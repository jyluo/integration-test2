#!/bin/bash

echo "Run for Sort07 + $1"
python experiment.py -g -rc -d "mini_$1" -p "Sort07,$1" &> "$1.txt"
