#!/bin/bash
# get_latest.sh — Update the local repo from GitHub

echo "[INFO] Updating repository"
git pull "https://github.com/nwayyanant/tipitaka-poc-starter.git"

if [ $? -ne 0 ]; then
  echo "[ERROR] git pull failed. Make sure this folder is a git repo cloned from the same URL."
  echo "        If not, run: git clone https://github.com/nwayyanant/tipitaka-poc-starter.git"
  exit 1
fi


echo "[OK] Repository is up to date."
