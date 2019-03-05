#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import os
import click
import time
import shutil
import os.path
from click import Context
from pathlib import Path
from subprocess import run, PIPE, DEVNULL
from rabird.core.configparser import ConfigParser
from configparser import NoSectionError, NoOptionError
from attrdict import AttrDict
from typing import Dict
from glob import glob


class TimeoutError(Exception):
    pass


class Application(object):
    def __init__(self):
        self._base_dir = Path(os.path.dirname(__file__)).parent.resolve()
        self._mysql_container_name = "%s_mysql_1" % self.base_dir.name

    @property
    def base_dir(self) -> Path:
        return self._base_dir

    @property
    def mysql_containter_name(self) -> str:
        return self._mysql_container_name

    def load_envs(self) -> Dict[str, str]:
        content = open("%s/.env" % self.base_dir).read()
        envs = dict()
        for line in content.splitlines():
            splitted = line.strip().split("=")
            envs[splitted[0].strip()] = splitted[1].strip()
        return envs

    def wait_mysql_started(self, timeout: float = 60):
        while timeout > 0:
            p = run(
                ["docker", "logs", self.mysql_containter_name],
                stderr=PIPE,
                stdout=DEVNULL,  # Keep silent!
                universal_newlines=True,
            )

            if "[Note] mysqld: ready for connections" in p.stderr:
                return

            time.sleep(1)
            timeout -= 1

        raise TimeoutError("Is image not started?")

    def start_docker_compose(self):
        run(["docker-compose", "down"], cwd=self.base_dir)
        run(["docker-compose", "up", "-d"], cwd=self.base_dir)

    def stop_docker_compose(self):
        run(["docker-compose", "down"], cwd=self.base_dir)

    def init_db(self):
        """Initialize database by default structure"""

        click.echo("Shutdown all 2BizBox containers ...")

        self.start_docker_compose()

        click.echo("Waitting MySQL started ...")
        self.wait_mysql_started()
        click.echo("MySQL started.")

        click.echo("Wait root user's password ready...")

        time.sleep(10)

        click.echo("Importing all database ...")

        run(
            'docker exec -i %s bash -c "mysql -u root --password=root"'
            % self.mysql_containter_name,
            input=open(
                str(self.base_dir / "server" / "db" / "database.sql"), "rb"
            ).read(),
            shell=True,
        )

        click.echo("Database import done! Wait for 5 seconds to stop ...")

        time.sleep(5)

        self.stop_docker_compose()


@click.group()
@click.pass_context
def main(ctx: Context):
    """2BizBox dockerized runtime framework manage program"""

    ctx.obj = Application()


@main.command()
@click.pass_obj
def start(app: Application):
    """Start server"""

    # Fixs jboss connection settings if it's not changed
    ds_cfg_path = os.path.join(
        app.base_dir, "server/jboss/server/default/deploy/mysql-ds.xml"
    )
    with open(ds_cfg_path) as f:
        content = f.read()
        orig_connection = "localhost:3307"

    if orig_connection in content:
        click.echo("Fixing MySQL connection settings ...")

        # Do settings backup first
        shutil.copy(ds_cfg_path, ds_cfg_path + ".old")
        with open(ds_cfg_path, "w") as f:
            f.write(content.replace(orig_connection, "mysql:3306"))

    # Fixs my.cnf
    orig_my_cnf_path = os.path.join(app.base_dir, "server/db/my.ini")

    my_cnf_dir = os.path.join(app.base_dir, "server/db/conf")
    my_cnf_path = os.path.join(my_cnf_dir, "my.cnf")
    os.makedirs(my_cnf_dir, exist_ok=True)

    if not os.path.exists(my_cnf_path):
        click.echo("Fixing MySQL server configs ...")

        cfg = ConfigParser(allow_no_value=True)
        cfg.read([orig_my_cnf_path])

        # Removed options that does not existed in MySQL 5.5
        try:
            cfg.remove_option("mysqld", "myisam_max_extra_sort_file_size")
        except NoSectionError:
            pass

        # Removed ports settings (Set to default 3306)
        try:
            cfg.remove_option("mysqld", "port")
        except NoSectionError:
            pass

        try:
            cfg.remove_option("client", "port")
        except NoSectionError:
            pass

        try:
            cfg.remove_option("mysqld", "log-bin")
        except NoSectionError:
            pass

        try:
            cfg.remove_option("mysqld", "basedir")
        except NoSectionError:
            pass

        # Renamed options
        if cfg.has_option("mysqld", "default-character-set"):
            cfg.set(
                "mysqld",
                "character-set-server",
                cfg.get("mysqld", "default-character-set"),
            )

            try:
                cfg.remove_option("mysqld", "default-character-set")
            except NoSectionError:
                pass

        # Force values:
        cfg.set("mysqld", "datadir", "/var/lib/mysql/")
        cfg.set("mysqld", "innodb_data_home_dir", "/var/lib/mysql/")

        cfg.write(open(my_cnf_path, "w"), space_around_delimiters=False)

    envs = app.load_envs()
    data_dir = envs["SERVICE_DATA_DIR"]
    if not glob(os.path.join(data_dir, "ibdata*")):
        # If there don't have `ibdata*` files in data directory, that means
        # the database not been initialize correctly.

        app.init_db()

    # Really start the server
    click.echo("Starting 2BizBox server ...")

    app.start_docker_compose()


@main.command()
@click.pass_obj
def stop(app: Application):
    """Stop server"""

    app.stop_docker_compose()


if __name__ == "__main__":
    main()
