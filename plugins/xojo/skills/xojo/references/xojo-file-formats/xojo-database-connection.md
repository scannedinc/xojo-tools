# `.xojo_database_connection`

An IDE-managed database connection. Four engines are defined — SQLite, MySQL, PostgreSQL and ODBC — and they share one region, one block structure and one set of top-level fields, differing only in which fields a connection set carries and how their values are written.

```text
#tag DatabaseConnection 1
AutoConnect = False
Stage = 0
ImplicitInstance = True
Begin ConnectionSet
	EncryptionKey = 
	FullPath = 
	MetaData = 
	Name = Development
	LoadExtensions = False
	ThreadYieldInterval = 0
	Timeout = 10
	WriteAheadLogging = False
End
Begin ConnectionSet
	...
End
#tag EndDatabaseConnection
```

The `1` after `DatabaseConnection` is a format version; preserve it. Connection-set fields are indented with one tab.

## Manifest kind and block tag

Each engine is a distinct project item kind, and a distinct RbBF block:

| Manifest kind | XML block `type` | RbBF block |
| --- | --- | --- |
| `SQLiteLocalConnection` | `SQLiteLocalConnection` | `pDC2` |
| `MySQLConnection` | `MySQLConnection, ` | `pDC3` |
| `PostgreSQLConnection` | `PostgreSQLConnection` | `pDC1` |
| `ODBCConnection` | `ODBCConnection` | `pDC4` |

The XML block `type` for a MySQL connection is written with a trailing comma and space. Nothing else in the format spells a type that way, and the value is not trimmed: a reader matching this type must match it exactly, and a writer must reproduce it.

## Top-level fields

`AutoConnect`, `Stage`, `ImplicitInstance` and `PerSession`, written in that order, before the first `Begin ConnectionSet`. Every engine writes them identically, and their values are unquoted.

`Stage` is an integer selecting the build stage a connection applies to: `0` Automatic, `1` Development, `2` Alpha, `3` Beta, `4` Final. `Automatic` resolves to whichever `ConnectionSet` matches the stage being built.

`PerSession` governs whether each web session gets its own connection, and only a web project writes it to text. A desktop project omits the line even though the same property is present in the binary and XML forms of that project, so its absence from a desktop file says nothing about whether the underlying property exists.

`AutoConnect` and `PerSession` are round-tripped correctly once they have been assigned a value, and a file that records either of them keeps it across any number of saves. In a newly created project, however, a switch the user has never touched can be written here as `False` while the same project's binary and XML forms both record `True`. A reader should therefore not treat these two fields in a freshly created project as authoritative where a binary or XML form of the same project exists, and a writer should record the values it actually holds.

## Connection sets

The `Begin` line is simply `Begin ConnectionSet`. A connection carries exactly four of them, one per deployment configuration, and the `Name` field selects which: `Development`, `Alpha`, `Beta`, or `Final`.

An empty value after `=` is distinct from an absent field. A field whose value is empty is still written, with nothing after the separator.

### Fields by engine

Each engine states its fields in a fixed order. The RbBF records live in a `conn` group.

| Engine | Text fields, in order |
| --- | --- |
| SQLite | `EncryptionKey`, `FullPath`, `MetaData`, `Name`, `LoadExtensions`, `ThreadYieldInterval`, `Timeout`, `WriteAheadLogging` |
| MySQL | `Name`, `Host`, `UserName`, `Password`, `DatabaseName`, `Port`, `Timeout`, `AutoConnect`, `MetaData` |
| PostgreSQL | `Name`, `Host`, `UserName`, `Password`, `DatabaseName`, `Port`, `Timeout`, `AppName`, `MultiThreaded`, `AutoConnect`, `MetaData` |
| ODBC | `Name`, `AutoConnect`, `ConnectionString`, `MetaData` |

The XML element and RbBF record for each field:

| Text field | XML element | RbBF | Engines |
| --- | --- | --- | --- |
| `Name` | `ItemName` | `name` | all |
| `MetaData` | `MetaData` | `Meta` | all |
| `FullPath` | `FullPath` | `path` | SQLite |
| `EncryptionKey` | `EncryptionKey` | `enky` | SQLite |
| `Timeout` | `Timeout` | `tout` | SQLite |
| `ThreadYieldInterval` | `ThreadYieldInterval` | `tyin` | SQLite |
| `LoadExtensions` | `LoadExtensions` | `ldex` | SQLite |
| `WriteAheadLogging` | `WriteAheadLogging` | `wahl` | SQLite |
| `Host` | `DBHost` | `dbhs` | MySQL, PostgreSQL |
| `UserName` | `DBUserName` | `dbUN` | MySQL, PostgreSQL |
| `Password` | `DBPassword` | `dbPW` | MySQL, PostgreSQL |
| `DatabaseName` | `DBName` | `dbnm` | MySQL, PostgreSQL |
| `Port` | `DBPort` | `dbpt` | MySQL, PostgreSQL |
| `Timeout` | `DBTimeout` | `dbto` | MySQL, PostgreSQL |
| `AppName` | `AppName` | `AppN` | PostgreSQL |
| `MultiThreaded` | `Multithreaded` | `Mult` | PostgreSQL |
| `AutoConnect` | `Autoconnect` | `auto` | MySQL, PostgreSQL, ODBC |
| `ConnectionString` | `ItemData` | `data` | ODBC |

`Timeout` is one text spelling over two representations: SQLite's is `Timeout`/`tout`, and the server engines' is `DBTimeout`/`dbto`.

The XML spells the multi-threading and auto-connect elements `Multithreaded` and `Autoconnect`, with a lowercase second word, where the text spells them `MultiThreaded` and `AutoConnect`. The difference is not a generational variant; each format uses its own spelling consistently.

Within a `conn` group SQLite states `MetaData` fourth, before its timeout fields, while the server engines state it last. A reader must not assume one position for it.

`AutoConnect` occurs both as a top-level field and, for the three server engines, as a field of each connection set. They are different properties: the top-level one is the connection item's own switch, and the per-set one belongs to that deployment configuration. In RbBF both are the `auto` record, distinguished by whether it sits in the block or in a `conn` group.

### Value form

SQLite writes every value unquoted. The other three engines quote every value except `MetaData`, which is unquoted like SQLite's.

```text
Begin ConnectionSet
	Name = "Development"
	Host = "127.0.0.1"
	UserName = ""
	Password = ""
	DatabaseName = ""
	Port = "3306"
	Timeout = "15"
	AutoConnect = "True"
	MetaData = 
End
```

A boolean is `True` or `False` in text and `1` or `0` in XML and RbBF. This applies to SQLite's `LoadExtensions` and `WriteAheadLogging`, to PostgreSQL's `MultiThreaded`, and to the per-set `AutoConnect`.

A newly created connection carries engine defaults: MySQL port `3306` with timeout `15`, PostgreSQL port `5432` with timeout `0` and `MultiThreaded` true, SQLite timeout `10`. All four sets of a new connection hold the same values, differing only in `Name`.
