#!/bin/bash 



################
##
## Script which adds filenames to file ARCHIVELIST, which
## is a spool file used to queue up archives.
## When populated, a routine call to 
## /usr/local/bin/fcsvr_trigger will perform archives
## of all files contained in our ARCHIVELIST
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
ARCHIVELIST="$SUPPORTPATH/filesToArchive"

if [ ! -f "$ARCHIVELIST" ]; then
	touch "$ARCHIVELIST"
	if [ "$?" != 0 ]; then
		echo "Could not create archive list at path: \"$ARCHIVELIST\" Exiting!"
		exit 1
	fi
elif [ ! -w "$ARCHIVELIST" ]; then
	echo "File at path: \"$ARCHIVELIST\" is not writeable!! Exiting!"
	exit 2
fi

echo "Using archive file at path: \"$ARCHIVELIST\""

if [ -z "$1" ]; then
	echo "Must be provided a file path to add to our archive list!! Exiting!"
	exit 3
fi	

## Make sure the path doesn't already exist in our list
CURRENTFILES="$("$cat" "$ARCHIVELIST")" 

## Change our IFS
IFS=$'\n'

## Disable Globbing
set -f   

## Check to see if our path contains our file already.
PATHEXISTS=0
for FILE in $CURRENTFILES; 
do
	if [ "$FILE" == "$1" ]; then
		PATHEXISTS=1
	fi
done

if [ "$PATHEXISTS" != 1 ]; then	
	echo "Adding file at path: \"$1\" to archive queue!"
	echo "$1" >> "$ARCHIVELIST" 
else
	echo "File at path: \"$1\" is already in the archive queue!"
fi

exit 0
