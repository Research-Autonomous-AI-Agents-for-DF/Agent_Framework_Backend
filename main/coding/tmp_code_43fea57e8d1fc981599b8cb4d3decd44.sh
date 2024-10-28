#!/bin/bash

image_file="dfr-01-ntfs.dd"
output_file="deleted_files.txt"

fls -o 0 $(echo "$image_file" | tr -d '[:space:]') > fls_output.txt
ils -r $(echo "$image_file" | tr -d '[:space:]') | grep Deleted | awk '{print $3}' > deleted_inodes.txt
ifind -i -o 0 $(echo "$image_file" | tr -d '[:space:]') < deleted_inodes.txt > ifind_output.txt
awk '{print $3}' ifind_output.txt > "$output_file"

rm fls_output.txt deleted_inodes.txt ifind_output.txt
cat "$output_file"