#!/bin/sh
# PRD.md(정본)에서 외부 의존성 없는 PRD.html을 만든다. 필요: pandoc
set -e
cd "$(dirname "$0")/.."
pandoc PRD.md -f gfm+yaml_metadata_block -t html5 --standalone --toc --toc-depth=2 \
  --template build/template.html --css build/prd.css --embed-resources -o PRD.html
echo "PRD.html 생성 완료"
