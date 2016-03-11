#!/bin/bash


################
##
## Script which adds filenames to file RESTORELIST, which
## is a spool file used to queue up archives.
## When populated, a routine call to 
## /usr/local/bin/fcsvr_trigger will perform archives
## of all files contained in our RESTORELIST
##
##############################

CONFIGFILE=/usr/local/etc/fcsArchiver.conf

declare -x cat='/bin/cat'
declare -x awk='/usr/bin/awk'

## Look for our config file
if [ ! -f "$CONFIGFILE" ]; then
	echo "Could not find config file at: $CONFIGFILE"
  exit 1
fi

## Extract our archive support path
SUPPORTPATH="$("$cat" "$CONFIGFILE" | "$awk" -F= '/^supportPath/{print$2'})"
RESTORELIST="$SUPPORTPATH/filesToRestore"

if [ ! -f "$RESTORELIST" ]; then
	touch "$RESTORELIST"
	if [ "$?" != 0 ]; then
		echo "Could not create archive list at path: \"$RESTORELIST\" Exiting!"
		exit 1
	fi
elif [ ! -w "$RESTORELIST" ]; then
	echo "File at path: \"$RESTORELIST\" is not writeable!! Exiting!"
	exit 2
fi

if [ -z "$1" ]; then
	echo "Must be provided a file path to add to our restore list!! Exiting!"
	exit 3
fi	

## Make sure the path doesn't already exist in our list
CURRENTFILES="$("$cat" "$RESTORELIST")" 

## Change our IFS
IFS=$'\n'

## Disable Globbing
set -f   

## Check to see if our path contains our file already.
for FILE in $("$cat" "$RESTORELIST"); 
do
	if [ "$FILE" == "$1" ]; then
		PATHEXISTS=1
	fi
done

if [ "$PATHEXISTS" != 1 ]; then	
	echo "Adding file at path: \"$1\" to restore queue!"
	echo "$1" >> "$RESTORELIST" 
else
	echo "File at path: \"$1\" is already in the restore queue!"
fi

exit 0
