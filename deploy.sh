#!/bin/bash
echo -e "\033[0;32mDeploying updates to GitHub...\033[0m"
hugo
cd public

## Ensure we have CNAME file for custom domain
# ssudake.com
# www.ssudake.com
echo "ssudake.com" > CNAME
echo "www.ssudake.com" >> CNAME

## Commit and push changes to GitHub
git add .
msg="Rebuilding site `date`"
if [ $# -eq 1 ]
  then msg="$1"
fi
git commit -m "$msg"
git push origin master
cd ..
