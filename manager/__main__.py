#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import os
import click
import time
import shutil
import os.path
import arrow
import zipfile
import tempfile
from click import Context
from pathlib import Path
from subprocess import run, PIPE, DEVNULL
from rabird.core.configparser import ConfigParser
from configparser import NoSectionError, NoOptionError
from attrdict import AttrDict
from typing import Dict, List
from glob import glob
from zipfile import ZipFile


def is_path_type(value):
    return isinstance(value, str) or isinstance(value, Path)


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

    @property
    def databases(self) -> List[str]:
        return [
            "bb2_test",
            "bb2_test_sg",
            "bb2_default",
            "bb2_default_sg",
            "bb2_def",
        ]

    def load_envs(self) -> Dict[str, str]:
        content = open("%s/.env" % self.base_dir).read()
        envs = dict()
        for line in content.splitlines():
            splitted = line.strip().split("=")
            # Skip empty lines or there do not have '=' symbol
            if len(splitted) < 2:
                continue

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

    def db_init(self):
        """Initialize database by default structure"""

        click.echo("Shutdown all 2BizBox containers ...")

        self.start_docker_compose()

        click.echo("Waitting MySQL started ...")
        self.wait_mysql_started()
        click.echo("MySQL started.")

        click.echo("Wait root user's password ready...")

        time.sleep(10)

        click.echo("Importing all database ...")

        self.db_import(str(self.base_dir / "server" / "db" / "database.sql"))

        click.echo("Database import done! Wait for 5 seconds to stop ...")

        time.sleep(5)

        self.stop_docker_compose()

    def db_dump(self, stdout, databases=[], force=False):
        cname = self.mysql_containter_name

        mysqldump_cmd = [
            "mysqldump",
            "-uroot",
            "-proot",
            "--opt",
            "--databases" if databases else "--all-databases",
            "--skip-lock-tables",
            "--hex-blob",
            "-f" if force else "",
            " ".join(databases),
        ]

        docker_cmd = 'docker exec -i %s bash -c "%s"' % (
            cname,
            " ".join(mysqldump_cmd),
        )

        return run(docker_cmd, stdout=stdout, shell=True)

    def db_import(self, sql_file, database=""):

        try:
            if is_path_type(sql_file):
                sql_file = open(str(sql_file), "rb")

            cname = self.mysql_containter_name

            mysql_cmd = ["mysql", "-uroot", "-proot", database]

            return run(
                'docker exec -i %s bash -c "%s"'
                % (cname, " ".join(mysql_cmd)),
                input=sql_file.read(),
                shell=True,
            )
        finally:
            if not is_path_type(sql_file):
                sql_file.close()


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

    # Fixs permissions of jboss directory
    run(
        [
            "docker-compose",
            "run",
            "--user=root",
            "-v",
            "%s:/opt/jboss" % os.path.join(app.base_dir, "server/jboss"),
            "--rm",
            # Don't run the linked mysql service!
            "--no-deps",
            "--entrypoint",
            "/bin/bash",
            "2bizbox",
            "-c",
            "chown -Rf jboss:jboss /opt/jboss",
        ]
    )
    app.stop_docker_compose()

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

        app.db_init()

    # Really start the server
    click.echo("Starting 2BizBox server ...")

    app.start_docker_compose()


@main.command()
@click.pass_obj
def stop(app: Application):
    """Stop server"""

    app.stop_docker_compose()


@main.command()
@click.argument("output_dir")
@click.pass_obj
def backup(app: Application, output_dir: str):
    """Backup the database"""

    click.echo("Backup now and it will take several minutes, please wait...")

    os.chdir(output_dir)

    file_name = arrow.now().format("YYYYMMDDHHmmss") + ".sql"
    with open(file_name, "wb") as f:
        p = app.db_dump(f, app.databases)
    if 0 != p.returncode:
        os.remove(file_name)
        click.echo(
            "Failed to dump database! \n"
            "Have you correctly start the 2BizBox server?!",
            err=True,
        )
        return p.returncode

    with ZipFile(file_name + ".zip", "w", zipfile.ZIP_LZMA) as sql_zip:
        sql_zip.write(file_name)
    os.remove(file_name)


@main.command()
@click.argument("input_file")
@click.pass_obj
def recover(app: Application, input_file: str):
    """Restore the database from input file.

    INPUT_FILE: Zipped SQL File which generated by backup command. Normally
    file with extension '.sql.zip'"""

    click.echo(
        "Importing now and it will take several minutes, please wait..."
    )

    temp_dir = tempfile.mkdtemp()
    try:
        with ZipFile(input_file, "r") as sql_zip:
            sql_zip.extractall(temp_dir)

        file_name = os.path.basename(input_file)
        file_name = os.path.splitext(file_name)[0]
        file_path = os.path.join(temp_dir, file_name)

        app.db_import(file_path)
    finally:
        shutil.rmtree(temp_dir)


@main.command()
@click.pass_obj
def default_to_test(app: Application):
    """Transfer Data From Default To Test"""

    import textwrap

    click.echo(
        textwrap.dedent(
            """\
            Export data from default and it will take several minutes, please
            wait...
            """
        ).replace("\n", " ")
    )

    temp_dir = tempfile.mkdtemp()
    try:
        sql_file_path = os.path.join(temp_dir, "default.sql")
        with open(sql_file_path, "w") as f:
            p = app.db_dump(f, databases=["bb2_default"], force=True)
        if p.returncode != 0:
            click.echo("Failed to export data!", err=True)
            return p.returncode
        click.echo("Export data successfully!")

        click.echo(
            textwrap.dedent(
                """\
                Import data to test and it will take several minutes,
                please wait...
                """
            ).replace("\n", " ")
        )

        p = app.db_import(sql_file_path, "bb2_test")
        if p.returncode != 0:
            click.echo("Import data to test fail!", err=True)
        click.echo("Import data to test successfully")

        with open(sql_file_path, "w") as f:
            p = app.db_dump(f, databases=["bb2_default_sg"], force=True)
        if p.returncode != 0:
            click.echo("Fail to export data!", err=True)

        click.echo("Export data successfully")

        click.echo(
            textwrap.dedent(
                """\
                Import data to test_sg and it will take several minutes,
                please wait...
                """
            ).replace("\n", " ")
        )

        p = app.db_import(sql_file_path, "bb2_test_sg")
        if p.returncode != 0:
            click.echo("Import data to test fail!", err=True)

        click.echo("Import data to test successfully")

        click.echo("Transfter data from default to test successfully!\n")

    finally:
        shutil.rmtree(temp_dir)


if __name__ == "__main__":
    main()
