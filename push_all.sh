#!/bin/bash
# 두 저장소에 동시에 푸시하는 스크립트

echo "Pushing to origin (khankorean)..."
git push origin main

echo "Pushing to oratio..."
git push oratio main

echo "All repositories updated!"
