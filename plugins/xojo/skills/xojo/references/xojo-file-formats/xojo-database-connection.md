# `.xojo_database_connection`

The IDE-managed SQLite local connection container is documented here. Other database engines and some stage options remain unassigned.

```text
#tag DatabaseConnection 1
AutoConnect = False
Stage = 0
ImplicitInstance = True
Begin ConnectionSet
   EncryptionKey =
   FullPath = Inventory.sqlite
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

The `1` after `DatabaseConnection` is a format/version value in the observed file; preserve it. Top-level fields are `AutoConnect`, `Stage`, `ImplicitInstance` and `PerSession`, written in that order.

`PerSession` governs whether each web session gets its own connection, and only a web project writes it. A desktop project omits the line even though the same property is present in the binary and XML forms of that project, so its absence from a desktop file says nothing about whether the underlying property exists.

`Stage` is an integer selecting the build stage a connection applies to: `0` Automatic, `1` Development, `2` Alpha, `3` Beta, `4` Final. `Automatic` resolves to whichever `ConnectionSet` matches the stage being built.

`AutoConnect` and `PerSession` are round-tripped correctly once they have been assigned a value, and a file that records either of them keeps it across any number of saves. In a newly created project, however, a switch the user has never touched can be written here as `False` while the same project's binary and XML forms both record `True`. A reader should therefore not treat these two fields in a freshly created project as authoritative where a binary or XML form of the same project exists, and a writer should record the values it actually holds.

The `Begin` line is simply `Begin ConnectionSet`; its unquoted `Name` field selects one of four deployment configurations: `Development`, `Alpha`, `Beta`, or `Final`. Each block has observed fields `EncryptionKey`, `FullPath`, `MetaData`, `Name`, `LoadExtensions`, `ThreadYieldInterval`, `Timeout`, and `WriteAheadLogging`. Values in this format are unquoted. An empty value after `=` is distinct from an absent field.

The manifest item kind is `SQLiteLocalConnection`. No PostgreSQL, MySQL, ODBC, remote SQLite, encrypted, or populated metadata example is present, so a general database-connection generator should begin with an IDE-created item of the required engine rather than extrapolate this schema.
