# Scripts are mainly used for stress testing of different databases,
# The way to test is to use Python modules to connect database then
# Repeatedly insert data.
#
# You can use this script in the following ways:
# such as:
#
#    python db_stresstesting_multi_thread.py -i <mysql_server_ipaddr> -u root \
#           -p <root_password> -P 3306 -d <database_name> \
#           -t [mysql|orace|sqlserver] -n <record_count> \
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
    p.add_option("-P", "--port", type="int", dest="port",
                 help="Input connect database port number.")
    p.add_option("-d", "--db", dest="db",
                 help="Input connect database name.")
    p.add_option("-t", "--type", dest="db_type",
                 help="Input connect database type."
                 "Such as [mysql|oracle|sqlserver].")
    p.add_option("-n", "--num", type="int", dest="total",
                 help="Enter the total number of test database inserts.")
    p.add_option("-C", "--clean", action="store_false", dest="clean_table",
                 help="Clean test database table")
    p.add_option("-D", "--debug", action="store_true", dest="open_debug",
                 help="Open sqlalchemy debug mode, The default is False")

    options, args = p.parse_args()

    if options.total is None:
        p.error("Pls test-database.py -h|--help")
        sys.exit(1)

    args = {"user": options.user,
            "password": options.password,
            "ip": options.ip,
            "port": options.port,
            "db": options.db,
            "db_type": options.db_type,
            "total": options.total,
            "clean_table": options.clean_table,
            "open_debug": options.open_debug}

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
        self._engine = self._get_engine(uri, debug)
        self._session = self.get_session()

    def create_database(self):
        Base.metadata.create_all(self._engine)

    def drop_database(self):
        Base.metadata.drop_all(self._engine)

    def add_test_data(self):
        start_date = datetime.utcnow()
        new_test = StressTestTable(date_time=start_date)
        self._session.add(new_test)
        self._session.commit()

    def query_data(self):
        data_total = self._session.query(
            func.count("*")).select_from(StressTestTable).scalar()

        return data_total

    def _get_engine(self, uri, debug=False):
        try:
            engine = create_engine(uri, pool_size=100, pool_recycle=7200,
                                   echo=debug)
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


def insert_record(test_obj, base_num):
    for _ in base_num:
        test_obj.add_test_data()
        logging.info(">>> Insert the %d commit data..." % base_num)


def thread_generator(th_num, test_obj, base_num):
    for th in xrange(th_num):
        yield threading.Thread(target=insert_record,
                               name=('Thread: %s' % th),
                               args=(test_obj, base_num))


@timer
def do_stress_test(connect_uri, **kwargs):
    """Start stress test database opeartion"""
    debug = kwargs['open_debug']
    th_num = kwargs["total"]
    base_num = 1024
    test_obj = StressTestDB(connect_uri, debug=debug)
    test_obj.create_database()

    try:
        threads = []
        for thread in thread_generator(th_num, test_obj, base_num):
            thread.start()
            threads.append(thread)

        for thread in threads:
            thread.join()

    except Exception:
        print "Failed to create thread. Quitting....."
        sys.exit(0)
    finally:
        db_total = test_obj.query_data()
        print "A total of %d data in Persons table" % db_total


def main():
    kwargs = parse_args()
    setup_logging()
    if kwargs["clean_table"] is False:
        do_clean_table()
        sys.exit(0)

    connect_uri = DB_CONNECT_URI.get(kwargs["db_type"]).format(**kwargs)
    do_stress_test(connect_uri, **kwargs)


if __name__ == "__main__":
    main()
