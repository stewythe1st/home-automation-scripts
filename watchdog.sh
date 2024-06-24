#!/bin/bash

thisdir=$(dirname -- "$( readlink -f -- "$0"; )";)
thisfile=$(basename $BASH_SOURCE)

if ps ax | grep -v "grep\|$thisfile" | grep $1 > /dev/null
then
    exit
else
    $thisdir/$1.py > $thisdir/$1.log 2>&1  &
fi

exit
