fls -o 0 dfr-01-ntfs.dd > fls_output.txt
ils -r dfr-01-ntfs.dd | grep Deleted | awk '{print $3}' > deleted_inodes.txt
ifind -i -o 0 dfr-01-ntfs.dd < deleted_inodes.txt > ifind_output.txt
awk '{print $3}' ifind_output.txt > deleted_files.txt

cat deleted_files.txt