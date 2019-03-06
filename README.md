# 2bb-studio

A runtime environment for 2BizBox server base on docker containers.

## Purpose

Base on this project, you could run 2BizBox server easily on any linux
environment (2BizBox only provied binary that support CentOS distributions).

## Installation

1. You must got an legal windows version 2BizBox binary that contained server
   installer (Only tested on 2BizBox 4.6)
2. Install 2BizBox server on windows or wine on linux
3. Clone this project to `/opt/2bb-studio` or any directory you want
4. Copy `server` directory under 2BizBox installation directory to
   `/opt/2bb-studio` directory
5. Create an `.env` file inside `/opt/2bb-studio` with this setting :

   ```bash
   SERVICE_DATA_DIR=/srv/2bb-studio
   SERVICE_ADDRESS=0.0.0.0
   ```

6. Ensure you have python3.6 or above installed
7. Install python requirements by command `pip3 install -r requirements.txt`
   under `/opt/2bb-studio`
8. Ensure you have docker installed
9. Done!

The final directory tree of `/opt/2bb-studio` will looks like:

```bash
/opt
|
+----2bb-studio
     |
     +---- manager # 2bb-studio Manager Program
     |     |
     |     +---- ...
     |
     +---- server # 2BizBox Installed Server Binaries
     |     |
     |     +---- conf # Generated during start command
     |     |     |
     |     |     +---- my.cnf
     |     |
     |     +---- ...
     |
     +---- docker-compose.yml
     +---- ...
```

## Usage

### Start Server

Start the 2BizBox server.

```bash
python3 -m manager start
```

This command will do these jobs before start the server:

1. Copy `my.ini` under `server/db/my.ini` to `server/conf/my.cnf`
2. Fix options in `my.cnf` that not working with MySQL 5.5 docker image
3. Initialize database if there does not have initialized database

### Stop Server

```bash
python3 -m manager stop
```

## License

All sources contained in this project are licensed under Apache License,
Version 2.0 (the "License");

You may obtain a copy of the License at <http://www.apache.org/licenses/LICENSE-2.0>
