# GooglePhotos Takeout Metadata Fixer

从Google Photos导出的照片可能会丢失meta data信息，这个project就是从导出文件里尽量补回这些信息的.
Fill Exif metadata from Google Photos supplemental-metadata.json files.

_**Usage**_: `gphoto_takeout_meta_fix [-h] [-r] [--dry-run] [--prune-json] [--version] directory`

_**positional arguments**_:   
    directory        Directory to process 

_**options**_:   
    -h, --help       show this help message and exit  
    -r, --recursive  Process subdirectories recursively   
    --dry-run        Show what would be written without modifying files   
    --prune-json     Delete JSON files that failed to match a media file   
    --version        show program's version number and exit   
