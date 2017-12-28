#!/usr/bin/env python
"""Commute Traffic Stats Processor."""
# pylint: disable=broad-except

from __future__ import print_function
import sys
import json
import logging
from datetime import datetime
import calendar
import pymysql
from pymysql.cursors import DictCursor
import yaml
import boto3
import statistics


# logging configuration
logging.getLogger().setLevel(logging.DEBUG)

# global
DATABASE_SCHEMA = 'schema.yml'
YEAR = 2017

try:
    SSM = boto3.client('ssm')

    PREFIX = '/commute'
    PARAMS = dict()
    for cat in ['database', 'config']:
        PARAMS[cat] = SSM.get_parameters_by_path(Path='%s/%s' % (PREFIX, cat),
                                                 Recursive=True, WithDecryption=True)
    logging.debug('ssm: parameters(%s)', PARAMS)

    DATABASE = dict()
    for param in PARAMS['database']['Parameters']:
        if '/database/' in param['Name']:
            key = param['Name'].replace('%s/database/' % PREFIX, '')
            DATABASE.update({key: param['Value']})
    logging.debug('ssm: database(%s)', DATABASE)

    ROUTES = dict()
    for param in PARAMS['config']['Parameters']:
        if '/config/routes' in param['Name']:
            ROUTES = json.loads(param['Value'])
    logging.info('ssm: routes(%s)', ROUTES)

    logging.info('ssm: successfully gathered parameters')
except ValueError as ex:
    logging.error('ssm: could not convert json routes (%s)', ex)
    sys.exit()
except Exception as ex:
    logging.error('ssm: could not connect to SSM. (%s)', ex)
    sys.exit()


try:
    CONNECTION = pymysql.connect(host=DATABASE['host'],
                                 user=DATABASE['user'],
                                 password=DATABASE['pass'],
                                 autocommit=True,
                                 cursorclass=DictCursor)
    logging.info('database: successfully connected to mysql')
except Exception as ex:
    logging.error('database: could not connect to mysql (%s)', ex)
    sys.exit()


def database_setup(dbc, schema):
    """Database setup."""
    logging.info('database: setup')
    for dbkey, dbval in schema['databases'].items():
        logging.info('database: check')
        sql = 'SHOW DATABASES'
        dbc.execute(sql)
        databases = dbc.fetchall()
        if {'Database': dbkey} not in databases:
            logging.warning('database: does not exist')
            logging.info('database: creating (%s)', dbkey)
            dbc.execute('CREATE DATABASE %s' % (dbkey))
        else:
            logging.info('database: exists')

        # use database
        dbc.execute('USE %s' % dbkey)

        # get tables
        logging.info('database: get tables')
        dbc.execute('SHOW TABLES')
        tables = dbc.fetchall()

        for tblkey, tblval in dbval['tables'].items():
            cols = ['%s %s %s' % (x, y['type'], y.get('options', '')) for x, y in tblval.items()]
            # create/validate table
            if {'Tables_in_%s' % DATABASE['name']: tblkey} not in tables:
                logging.warning('table: does not exist (%s)', tblkey)
                logging.info('table: creating (%s)', tblkey)
                sql = 'CREATE TABLE %s (%s)' % (tblkey, ', '.join(cols))
                logging.debug('table: %s', sql)
                dbc.execute(sql)
            else:
                logging.info('table: exists (%s)', tblkey)

            # validate columns
            dbc.execute('DESCRIBE %s' % tblkey)
            table = dbc.fetchall()

            def opts(pky):
                """Return and filter options."""
                return pky.get('Key', '').replace('PRI', 'PRIMARY KEY')
            tbl = ['%s %s %s' % (x['Field'], x['Type'], opts(x)) for x in table]

            if tbl == cols:
                logging.info('table: columns match schema')
            else:
                logging.error('table: columns do not match schema')
                sys.exit()
    logging.info('database: setup complete')


def query(dbc, date):
    """Query traffic."""
    logging.info('query traffic: %s', date)
    table = DATABASE['table']
    fields = ['duration_in_traffic']
    wheres = ['DAYNAME(timestamp) = "%s"' % date['day'],
              'MONTHNAME(timestamp) = "%s"' % date['month'],
              'YEAR(timestamp) = %s' % date['year']]
    where = ' AND '.join(wheres)
    sql = 'SELECT %s FROM %s WHERE %s' % (','.join(fields), table, where)
    logging.debug('query: %s' % sql)
    dbc.execute(sql)
    return dbc.fetchall()


def save(dbc, stats):
    """Save stats."""
    logging.info('save stats: %s', stats)
    return stats


def handler(event, context):
    """Lambda handler."""
    # pylint: disable=unused-argument
    logging.info('event %s', event)

    with open(DATABASE_SCHEMA) as schema_file:
        schema = yaml.load(schema_file)

    def combos():
        combo = list()
        for year in range(YEAR, int(datetime.utcnow().strftime('%Y')) + 1):
            for month in calendar.month_name[1:]:
                for day in calendar.day_name:
                    combo.append({'year': year, 'month': month, 'day': day})
        return combo

    def stat(key, vals):
        try:
            if 'min' in key:
               res = min(vals)
            elif 'max' in key:
               res = min(vals)
            else:
                res = getattr(statistics, key)(vals)
        except statistics.StatisticsError as ex:
            logging.warning('statistics: %s' % ex)
            return 0
        return res

    with CONNECTION.cursor() as cursor:
        # database setup
        database_setup(cursor, schema)
        # process
        logging.info('processing: start')
        for combo in combos():
            res = query(cursor, combo)
            vals = [z for x in res for y,z in x.items()]
            if not vals:
                vals = [0, 0]
            stypes = ['min', 'max', 'mean', 'median', 'median_low', 'median_high',
                      'median_grouped', 'mode', 'pstdev', 'pvariance', 'stdev', 'variance']
            data = dict()
            for stype in stypes:
                data[stype] = stat(stype, vals)
            print(data)
        logging.info('processing: end')
    return None


if __name__ == '__main__':
    print(handler({"trigger": "cli"}, None))
