import generators.postgres
import json
from flask import Flask, render_template, url_for

pg = generators.postgres.postgres_generator()


app = Flask(__name__)

def get_db_definition():
    dbdef = None
    try:
        dbdef = pg.get_database_definition(force_regen = False)[1]  # 0=df, 1 = dict
    except Exception as e:
        print(f'Exception: str({e})')
    finally:
        return dbdef


@app.route('/')
def show_schema():
    db_def = get_db_definition()

    # Parse the JSON strings in the dictionary
    for schema in db_def.values():
        for table in schema['tables'].values():
            table['columns'] = json.loads(table['columns'])
            table['constraints'] = json.loads(table['constraints'])
            table['index'] = json.loads(table['index'])

    return render_template('anaximander.html'
                            , page_title = 'Anaxaminder'
                            , document_title = 'Database Dictionary - Adventure Works'
                            , schemas = db_def)


if __name__ == '__main__':
    app.run(host='0.0.0.0', port=8090, debug=True)

