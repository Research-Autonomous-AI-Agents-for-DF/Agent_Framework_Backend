fls -o /dev/mapper/loop0p1 dfr-01-ntfs.dd > fls_output.txt
ils -r | grep Deleted | awk '{print $3}' > deleted_inodes.txt
ifind -i -o /dev/mapper/loop0p1 dfr-01-ntfs.dd < deleted_inodes.txt > ifind_output.txt
awk '{print $3}' ifind_output.txt > deleted_files.txt
rm fls_output.txt deleted_inodes.txt ifind_output.txt

cat deleted_files.txt