import configparser
from psycopg2 import OperationalError
import pandas as pd
from sqlalchemy import create_engine
import numpy as np
import json
import os
from datetime import datetime


'''
Builds a json structure of the target database defined in the config file 
'''

class postgres_generator:

    definition_keep_alive_days = -1
    db_definition_file = ''

    def __init__(self, config_file: str = 'config.cfg'):
        config = configparser.ConfigParser()
        config.read(config_file)

        if not config.has_section('postgres'):
            raise ValueError('Section \'postgres\' missing in configuration')

        reqd_params = ['host', 'database', 'user', 'password']
        for option in reqd_params:
            if not config.has_option('postgres', option):
                raise ValueError(f'Parameter \'{option}\' in section \'postgres\'')

        self.pg_conn_config = {
            'host': config.get('postgres', 'host'),
            'database': config.get('postgres', 'database'),
            'user': config.get('postgres', 'user'),
            'password': config.get('postgres', 'password'),
            'port': config.get('postgres', 'port', fallback='5432')
        }
        self.definition_keep_alive_days = int(config.get('postgres', 'definition_keep_alive_days'))
        self.db_definition_file = config.get('postgres', 'db_definition_file')


    def get_pg_connection(self):
        try:
            engine = create_engine(f"postgresql://{self.pg_conn_config['user']}:{self.pg_conn_config['password']}@{self.pg_conn_config['host']}:{self.pg_conn_config['port']}/{self.pg_conn_config['database']}")
            return engine
        except OperationalError as e:
            raise ConnectionError(f'Postgres connection issue: {str(e)}')


    def get_columns(self, df, schema, table):
        dfcols = df[(df.table_schema==schema) & (df.table_name==table) & (df.parameter_type!='index')][['column_name', 'column_position', 'data_type', 'is_nullable','is_identity', 'pk','fk','uq','default_value', 'description']]
        dfcols.sort_values(by=['column_position'], inplace=True)
        retval = dfcols.to_json(orient='records')
        return retval


    def get_indexes(self, df, schema, table):
        dfndxs = df[(df.table_schema==schema) & (df.table_name==table) & (df.parameter_type=='index')][['index_name', 'index_type', 'index_columns']]
        retval = dfndxs.to_json(orient='records')
        return retval


    def get_constraints(self, df, schema, table):
        dfcons = df[(df.table_schema==schema) & (df.table_name==table) & (df.parameter_type=='constraint')][['constraint_name', 'constraint_type', 'column_name' , 'fk_references']]
        retval = dfcons.to_json(orient='records')
        return retval


    def default_table_structure(self):
        return {
                'name':''
                , 'columns':{}
                , 'index':{}
                , 'constraints': {}
                }

    def get_tables(self, df, schema):
        ndtables = df[df.table_schema==schema].table_name.unique()
        tables = {ndtbl: self.default_table_structure() for i, ndtbl in enumerate(ndtables)}
        for table,cols in tables.items():
            tables[table]['name'] = table
            tables[table]['columns'] = self.get_columns(df, schema, table)
            tables[table]['index'] = self.get_indexes(df, schema, table)
            tables[table]['constraints'] = self.get_constraints(df, schema, table)
        return tables


    def default_schema_structure(self):
        return {
                'name':''
                , 'tables':{}
                }

    def get_schemas(self, df):
        ndschemas = df.table_schema.unique()
        schemas = {sch: self.default_schema_structure() for i, sch in enumerate(ndschemas)}
        for schema, tables in schemas.items():
            schemas[schema]['name'] = schema
            schemas[schema]['tables'] = self.get_tables(df, schema)
        return schemas


    def build_structure(self):
        schemas = {}
        try:
            #get data
            engine = self.get_pg_connection()
            print('Connected to database')
            qry = open('queries/postgres.sql', 'r').read()
            dfdata = pd.read_sql_query(qry, engine, index_col=None)
            dfdata = dfdata.reset_index(drop=True)
            dfdata.replace(np.nan, ' ', inplace=True)
            dfdata['description'] = ' '  # adding column which later can be populated relevantly
                                         # or if database has comments can read those if required
                                         # note that this requires altering the sql statement
            print('Data query successful')

            # process the data
            schemas = self.get_schemas(dfdata)

            #rename columns
            dfdata = dfdata.rename(columns={  'table_schema' : 'Schema'
                                            , 'table_name' : 'Table'
                                            , 'column_name' : 'Column'
                                            , 'column_position' : 'column_position'
                                            , 'data_type' : 'Data Type'
                                            , 'is_nullable' : 'Not Null'
                                            , 'is_identity' : 'Identity'
                                            , 'pk' : 'pk'
                                            , 'fk' : 'fk'
                                            , 'uq' : 'uq'
                                            , 'default_value' : 'Default Value'
                                            , 'constraint_type' : 'Constraint Type'
                                            , 'constraint_name' : 'Constraint Name'
                                            , 'fk_references' : 'References'
                                            , 'parameter_type' : 'parameter_type'
                                            , 'index_name' : 'Index Name'
                                            , 'index_type' : 'Index Type'
                                            , 'index_columns' : 'Columns'
                                            , 'description' : 'Description'})
            dfdata.to_csv(f'def{self.db_definition_file}.csv', index=False)

            # save json
            with open(f'def{self.db_definition_file}.json', 'w') as file:
                json.dump(schemas, file)

        except Exception as e:
            print(f'Error: {str(e)}')

        finally:
            return (dfdata, schemas) #df, dict


    def get_database_definition(self, force_regen:bool=False):
        # the structure is saved to a file
        # if the file is older than definition_keep_alive_days OR force_regen = True then we regen

        readfile = False
        writefile = False

        database_definitions = () # empty tuple

        if os.path.exists(f'def{self.db_definition_file}.csv'):
            if (datetime.now() - datetime.fromtimestamp(
                    os.path.getmtime(f'def{self.db_definition_file}.csv'))).days > self.definition_keep_alive_days\
                    or force_regen:
                writefile = True
            else:
                readfile = True
        else:
            writefile = True

        if readfile:
            # load dataframe
            database_definition_df = pd.read_csv(f'def{self.db_definition_file}.csv')
            # load json
            with open(f'def{self.db_definition_file}.json', 'r') as file:
                database_definition_json = json.load(file) #dict

            database_definitions = (database_definition_df, database_definition_json)

        if writefile:
            database_definitions  = self.build_structure()

        return database_definitions # df, dict
