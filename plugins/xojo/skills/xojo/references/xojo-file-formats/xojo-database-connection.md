# `.xojo_database_connection`

The IDE-managed SQLite local connection container is documented here. Other database engines and some stage options remain unassigned.

```text
#tag DatabaseConnection 1
AutoConnect = False
Stage = 0
ImplicitInstance = True
Begin ConnectionSet
   EncryptionKey =
   FullPath = EddiesElectronics.sqlite
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
Begin ConnectionSet
   ...
End
Begin ConnectionSet
   ...
End
#tag EndDatabaseConnection
```

The `1` after `DatabaseConnection` is a format/version value in the observed file; preserve it. Top-level fields are `AutoConnect`, `Stage`, and `ImplicitInstance`.

The `Begin` line is simply `Begin ConnectionSet`; its unquoted `Name` field selects one of four deployment configurations: `Development`, `Alpha`, `Beta`, or `Final`. Each block has observed fields `EncryptionKey`, `FullPath`, `MetaData`, `Name`, `LoadExtensions`, `ThreadYieldInterval`, `Timeout`, and `WriteAheadLogging`. Values in this format are unquoted. An empty value after `=` is distinct from an absent field.

The manifest item kind is `SQLiteLocalConnection`. No PostgreSQL, MySQL, ODBC, remote SQLite, encrypted, or populated metadata example is present, so a general database-connection generator should begin with an IDE-created item of the required engine rather than extrapolate this schema.
