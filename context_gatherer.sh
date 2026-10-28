#!/usr/bin/env bash

i=0

while [ -f "context$i.md" ]; do
  i=$((i + 1))
done

output="context$i.md"

find . -type f \
  ! -path '*/.*' \
  ! -name 'context.md' \
  ! -name 'context_gatherer.sh' \
  ! -name "$output" \
  -exec sh -c '
    for f do
      printf "\n## %s\n\n" "${f#./}"
      markitdown "$f"
    done
  ' sh {} + >> "$output"