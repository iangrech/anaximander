with constraint_defs as
(
	select
		tc.table_catalog dbname
		, tc.constraint_name
	    , tc.constraint_type
		, tc.table_schema 	constraint_table_schema
	    , tc.table_name 	constraint_table_name
	    , kcu.column_name 	constraint_column
	    , ccu.table_name 	referenced_table
	    , ccu.column_name 	referenced_column
	from
	    information_schema.table_constraints tc
			inner join information_schema.key_column_usage kcu
			    on tc.constraint_name = kcu.constraint_name
			left outer join information_schema.constraint_column_usage ccu
				on kcu.constraint_name = ccu.constraint_name
	where
	    tc.table_schema not in ('pg_catalog', 'information_schema')
), column_defaults as
(
	select
		  split_part(a.attrelid::regclass::text, '.', 1) table_schema
		, split_part(a.attrelid::regclass::text, '.', 2) table_name
		, a.attname column_name
		, pg_get_expr(d.adbin, d.adrelid) AS default_value
	from
		pg_catalog.pg_attribute    a
			left outer join pg_catalog.pg_attrdef d
				on (a.attrelid, a.attnum) = (d.adrelid, d.adnum)
	where
		not a.attisdropped           -- no dropped (dead) columns
		and a.attnum   > 0           -- no system columns
		and pg_get_expr(d.adbin, d.adrelid) is not null
), pgindexes as
(
	select
	    i.schemaname table_schema
		, i.tablename table_name
		, i.indexname index_name
		, substring(i.indexdef FROM 'USING(.*?)\(') ndx_type
		, substring(i.indexdef FROM '\((.*?)\)') ndx_columns
	from
		pg_indexes i
			left outer join
				(
				  select *
				  from constraint_defs cd
				  where cd.constraint_type = ('PRIMARY KEY')
				) cds
					on i.indexname = cds.constraint_name
	where
		i.schemaname not in ('pg_catalog', 'information_schema')
		and cds.constraint_name is null -- do not include Primary Keys
)
select
	c.table_schema
	, c.table_name
	, c.column_name
	, c.ordinal_position column_position
	, c.data_type
	, case when c.is_nullable = 'NO' then '' else 'Y' end is_nullable
	, case when c.is_identity = 'NO' then 'N' else 'Y' end is_identity
	, case when cons.constraint_type = 'PRIMARY KEY' then 'Y' else '' end pk
	, case when cons.constraint_type = 'FOREIGN KEY' then 'Y' else '' end fk
	, case when cons.constraint_type = 'UNIQUE' then 'Y' else '' end uq
	, cd.default_value
	, cons.constraint_type
	, cons.constraint_name
	, case
		when cons.constraint_type = 'FOREIGN KEY' then cons.referenced_table || '.' || cons.referenced_column
	    else ''
	  end fk_references
	, case
		when cons.constraint_type = 'PRIMARY KEY' then 'constraint'
		when cons.constraint_type = 'FOREIGN KEY' then 'constraint'
		when cons.constraint_type = 'UNIQUE' then 'index'
		else ''
	  end parameter_type
	, null index_name
	, null index_type
	, null index_columns
from
	information_schema.columns c
		left outer join column_defaults cd
			on cd.table_schema = c.table_schema
				and cd.table_name = c.table_name
				and cd.column_name = c.column_name
		left outer join constraint_defs cons
			on cons.constraint_table_schema  = c.table_schema
				and cons.constraint_table_name = c.table_name
				and cons.constraint_column = c.column_name
where
	c.table_schema not in ('pg_catalog', 'information_schema')
union
	select
		i.table_schema
		, i.table_name
		, null column_name
		, null ordinal_position
		, null data_type
		, null is_nullable
		, null is_identity
		, null pk
		, null fk
		, null uq
		, null default_value
	    , null constraint_type
		, null constraint_name
		, null fk_references
		, 'index' parameter_type
		, i.index_name
		, i.ndx_type
		, i.ndx_columns
	from
		pgindexes i
order by
	table_schema
	, table_name
	, column_name
	, index_name
