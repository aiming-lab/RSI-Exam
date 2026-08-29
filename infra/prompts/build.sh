#!/bin/bash
# Regenerate autoresearch.j2 from autoresearch.md. Run after editing the .md.
cd "$(dirname "$0")"
{
  cat autoresearch.md
  echo
  echo "================================ TASK ================================"
  echo
  echo "{{ instruction }}"
  echo
  echo "This program and the task are also on disk, at /app/AUTORESEARCH.md and /app/TASK.md. Re-read them whenever you need the exact interface, rules, or how you are meant to work."
} > autoresearch.j2
echo "autoresearch.j2 regenerated ($(wc -c < autoresearch.j2) bytes)"
