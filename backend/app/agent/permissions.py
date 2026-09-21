from enum import Enum


class ToolPermission(str, Enum):
    READ = "read"
    WRITE = "write"
    DESTRUCTIVE = "destructive"
