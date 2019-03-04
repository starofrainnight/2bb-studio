#!/bin/bash

get_script_dir() {
    local SOURCE="${BASH_SOURCE[0]}"
    local DIR=""

    # resolve $SOURCE until the file is no longer a symlink
    while [ -h "$SOURCE" ]; do
        DIR="$( cd -P "$( dirname "$SOURCE" )" && pwd )"
        SOURCE="$(readlink "$SOURCE")"
        # if $SOURCE was a relative symlink, we need to resolve it relative to the
        # path where the symlink file was located
        [[ $SOURCE != /* ]] && SOURCE="$DIR/$SOURCE"
    done
    DIR="$( cd -P "$( dirname "$SOURCE" )" && pwd )"

    # Return directory from function
    echo "$DIR"
}

SCRIPT_DIR="$(get_script_dir)"

cd ${SCRIPT_DIR}
python3 -m manager %*
