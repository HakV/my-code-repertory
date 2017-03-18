#!/usr/bin/env python
# Scripts are mainly used for stress testing of different databases,
# The way to test is to use Python modules to connect database then
# Repeatedly insert data.
#
# You can use this script in the following ways:
# such as:
#
#    python db_stresstesting_multi_thread.py -i <mysql_server_ip> -u root \
#           -p password -P 3306 -d test -t mysql -n 100 \
#           [-C "clean test db table"|-D "open debug" ]
#
# Code is reconstructed for test database
# Defines the general class of the operating database, call Opeartion_DB class
# can More flexible access to create, delete, add users and other operations

from datetime import datetime
import functools
import logging
import optparse
import os
import sys
import time
import threading

from sqlalchemy import create_engine
from sqlalchemy import func, Column, Integer, String
from sqlalchemy.orm import sessionmaker, scoped_session
from sqlalchemy.ext import declarative

Base = declarative.declarative_base()

DB_CONNECT_URI = {"mysql": "mysql://{user}:{password}@{ip}:{port}/{db}",
                  "oracle": "oracle://{user}:{password}@{ip}:{port}/{db}",
                  "sqlserver": "mssql+pymssql://{user}:{password}@{ip}"}


def timer(func):

    @functools.wraps(func)
    def wrapper(*args, **kwargs):
        start_time = time.time()
        func(*args, **kwargs)
        end_time = time.time()
        print "Timer: %s" % (end_time - start_time)

    return wrapper


def setup_logging():
    """Edit log configure file && output format"""

    log_path = os.getcwd()
    logging.basicConfig(level=logging.DEBUG,
                        format="%(asctime)s %(filename)"
                               "s[line:%(lineno)d] {%(threadName)s} "
                               "%(levelname)s %(message)s",
                        datefmt="%a, %d %b %Y %H:%M:%S",
                        filename="%s/db_stresstesting.log" % log_path,
                        filemode="w")


def parse_args():
    """The function define how to use this scipt andProvide help manual"""

    usage = "usage: %prog [options] arg1 ... arg2"
    p = optparse.OptionParser(usage=usage)

    p.add_option("-i", "--ip", dest="ip",
                 help="Input an ip connect address.")
    p.add_option("-u", "--user", type="string", dest="user",
                 help="Input connect database test user.")
    p.add_option("-p", "--password", dest="password",
                 help="Input connect database user password")
    p.add_option("-P", "--port", type="int",
                 dest="port", default=3306,
                 help="Input connect database port number, default is 3306")
    p.add_option("-d", "--db", dest="db",
                 help="Input connect database name.")
    p.add_option("-t", "--type", dest="db_type", default="mysql",
                 help="Input connect database type."
                 "Such as [mysql|oracle|sqlserver], default is mysql")
    p.add_option("-c", "--thread_count", type="int",
                 dest="thread_count", default=100,
                 help="Enter the total number of test database inserts."
                 " default is 100 thread count")
    p.add_option("-C", "--clean", action="store_false", dest="clean_table",
                 help="Clean test database table")
    p.add_option("-D", "--debug", action="store_true", dest="debug",
                 help="Open sqlalchemy debug mode, The default is False")

    options, args = p.parse_args()

    if options.db is None:
        p.error("Pls test-database.py -h|--help")
        sys.exit(1)

    args = {"user": options.user,
            "password": options.password,
            "ip": options.ip,
            "port": options.port,
            "db": options.db,
            "db_type": options.db_type,
            "thread_count": options.thread_count,
            "clean_table": options.clean_table,
            "debug": options.debug}

    return args


class StressTestTable(Base):
    """Define a database Persons table for use test"""

    __tablename__ = "Streetest_table"

    id = Column(Integer, primary_key=True)
    date_time = Column(String(30), default=datetime.utcnow())


class StressTestDB(object):
    """Define stress test operation database the same class"""

    def __init__(self, uri, debug=False):
        self.uri = uri
        self.debug = debug
        self._engine = self.get_engine()
        self.session = self.get_session()

    def create_database(self):
        Base.metadata.create_all(self._engine)

    def drop_database(self):
        Base.metadata.drop_all(self._engine)

    def add_test_data(self):
        start_date = datetime.utcnow()
        new_test = StressTestTable(date_time=start_date)
        self.session.add(new_test)
        self.session.commit()

    def query_data(self):
        data_total = self.session.query(
            func.count("*")).select_from(StressTestTable).scalar()

        return data_total

    def get_engine(self):
        try:
            engine = create_engine(self.uri, pool_size=100,
                                   pool_recycle=7200, echo=self.debug)
        except Exception as err:
            logging.info(">>> %s" % err)
        return engine

    def get_session(self):
        session = scoped_session(sessionmaker(bind=self._engine,
                                              autoflush=True))
        return session


def do_clean_table(connect_uri):
    begin_test = StressTestDB(connect_uri)
    begin_test.drop_database()


def insert_record(test_obj, num):
    test_obj.add_test_data()
    logging.info(">>> Insert the %d commit data..." % num)


@timer
def do_stress_test(connect_uri, **kwargs):
    """Start stress test database opeartion"""
    debug = kwargs.get("debug")
    test_obj = StressTestDB(connect_uri, debug=debug)
    test_obj.create_database()
    try:
        for thread_num in xrange(kwargs.get("thread_count")):
            threading.Thread(target=insert_record,
                             name=('Thread: %s' % thread_num),
                             args=(test_obj, thread_num)).start()
        test_obj.session.close()

    # Test process, if you want to interrupt the program,
    # you can output friendly
    except KeyboardInterrupt:
        print "Quitting....."
        sys.exit(0)
    finally:
        begin_test = StressTestDB(connect_uri, debug)
        db_total = begin_test.query_data()
        begin_test._session.close()
        print "A total of %d data in Streetest_table table" % db_total


def main():
    kwargs = parse_args()
    connect_uri = DB_CONNECT_URI.get(kwargs.get("db_type")).format(**kwargs)
    setup_logging()
    if kwargs.get("clean_table") is False:
        do_clean_table(connect_uri)
        sys.exit(0)

    do_stress_test(connect_uri, **kwargs)


if __name__ == "__main__":
    main()
