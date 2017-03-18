"""
Script for sync SmartWiki Documents into DokuWiki.
"""

import logging
import os
import optparse
import sys
from urllib import quote

from sqlalchemy import BIGINT, create_engine, Column, DateTime, Integer, String
from sqlalchemy import Text, TIMESTAMP
from sqlalchemy.ext import declarative
from sqlalchemy.orm import sessionmaker

reload(sys)
sys.setdefaultencoding("utf-8")

SQLALCHEMY_DATABASE_URI = ('mysql+pymysql://smartwiki:'
                           'smartwiki@<mysql_server_ipaddr>:3306/smartwiki?charset=utf8')
SMARTWIKI_SERVER_IPADDR = '<smartwiki_server_ipaddr>'
_ENGINE = None
_SESSION_MAKER = None

Base = declarative.declarative_base()


class WKDocument(Base):
    """Table wt_document from database of smartwiki."""

    __tablename__ = 'wk_document'
    doc_id = Column(BIGINT, primary_key=True)
    doc_name = Column(String(200), nullable=False)
    parent_id = Column(BIGINT, nullable=False)
    project_id = Column(Integer, nullable=False)
    doc_sort = Column(Integer, nullable=False)
    doc_content = Column(Text)
    create_time = Column(DateTime)
    create_at = Column(Integer, nullable=False)
    modify_time = Column(DateTime)
    modify_at = Column(Integer)
    version = Column(TIMESTAMP, nullable=False)


def _get_engine():
    """Get the globally unique engine object."""

    global _ENGINE
    if _ENGINE is not None:
        logging.debug("SQLAlchemy engine %s exist.", _ENGINE)
        return _ENGINE
    logging.debug("Create new SQLAlchemy engine.")
    _ENGINE = create_engine(SQLALCHEMY_DATABASE_URI)
    return _ENGINE


def _get_session_maker(engine):
    """Get the globally unique sessionmaker class."""

    global _SESSION_MAKER
    if _SESSION_MAKER is not None:
        logging.debug("SQLAlchemy session maker %s exist.", _SESSION_MAKER)
        return _SESSION_MAKER
    logging.debug("Create new SQLAlchemy session maker.")
    _SESSION_MAKER = sessionmaker(bind=engine)
    return _SESSION_MAKER


def get_session():
    """Get a session of database."""

    logging.info("Get the SQLAlchemy session object.")
    engine = _get_engine()
    session_maker = _get_session_maker(engine)
    session = session_maker()
    return session


def sw_to_dw(session=None):
    """Sync the smartwiki document to dokuwiki."""

    logging.info("Start to sync the smartwiki documents to dokuwiki.")
    doku_pages_path = '/var/www/dokuwiki/data/pages'
    if not session:
        session = get_session()
    try:
        for doc in session.query(WKDocument).all():
            if doc.doc_content:
                file_name = ''.join([quote(doc.doc_name.encode('utf8')),
                                     '.txt'])
                file_full_path = os.path.join(doku_pages_path, file_name)

                with open(file_full_path, 'w') as file_obj:
                    try:
                        content = ''.join(['[[', SMARTWIKI_SERVER_IPADDR,
                                           '/docs/show/',
                                           str(doc.doc_id),
                                           '|Smartwiki Link]] \n \n',
                                           doc.doc_content])
                        file_obj.write(content)
                    except Exception as err:
                        logging.exception("Failed to sync the smartwiki "
                                          "documents to dokuwiki, detailed "
                                          "error as %s", err)
                try:
                    os.system(''.join(['sudo chown www-data:www-data ',
                                       file_full_path]))
                except Exception as err:
                    logging.exception("Failed to change owner as www-data for "
                                      "%s", file_full_path)
    finally:
        session.close()
        logging.info("Sync the smartwiki documents to dokuwiki successfully")


def parse_args(argv):
    """Parses commaond-line arguments"""
    parser = optparse.OptionParser()
    parser.add_option('-d', '--debug', action='store_true',
                      dest='debug', default=False,
                      help='Enable debug message.')
    return parser.parse_args(argv[1:])[0]


def main(argv):
    os.environ['LANG'] = 'en_US.UTF8'
    option = parse_args(argv)
    if option.debug:
        log_level = logging.DEBUG
    else:
        log_level = logging.INFO
    logging.basicConfig(level=log_level,
                        format='%(asctime)s-%(filename)s '
                               '%(levelname)s %(message)s',
                        datefmt='%a, %d/%b/%Y-%H:%M:%S',
                        filename='sync_sw_2_dw.log',
                        filemode='w')

    sw_to_dw()
    print 'Done to sync smartWiki documents to dokuwiki!'


if __name__ == '__main__':
    main(sys.argv)
