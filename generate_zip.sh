#!/bin/bash

rm Import-LIB-KiCad-Plugin.zip

jq --arg today "$(date +%Y-%m-%d)" '.versions[0].version |= $today' metadata.json > metadata.json

git ls-files  -- 'metadata.json' 'resources*.png' 'plugins*.png' 'plugins*.py' | xargs zip Import-LIB-KiCad-Plugin.zip