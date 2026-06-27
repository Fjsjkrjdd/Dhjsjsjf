#!/bin/bash
# Сборка архива для загрузки на хостинг (файлы сразу в корне архива).
set -euo pipefail
cd "$(dirname "$0")"
rm -f chernova-psiholog-site.zip
(cd php-site && zip -r ../chernova-psiholog-site.zip . \
  -x "data/site.sqlite" "data/*.sqlite" "uploads/*" ".git/*")
echo "Готово: chernova-psiholog-site.zip ($(du -h chernova-psiholog-site.zip | cut -f1))"
