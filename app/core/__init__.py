"""app/core/ — Cross-cutting concerns: configuration and security.

Nothing outside app/core/config.py reads os.environ directly. Every other
module receives configuration through the Settings object (dependency
injection) or through the existing Sprint 1-6 *Config.from_env() classes.
"""
