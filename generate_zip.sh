#!/bin/bash

rm Import-LIB-KiCad-Plugin.zip
mv metadata.json metadata_.json
jq --arg today "$(date +%Y.%m.%d)" '.versions[0].version |= $today' metadata_.json > metadata.json

git ls-files  -- 'metadata.json' 'resources*.png' 'plugins*.png' 'plugins*.py' | xargs zip Import-LIB-KiCad-Plugin.zip
mv metadata_.json metadata.json