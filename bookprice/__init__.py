__version__ = "0.6.1"

# Bump when an update needs packages the installed program does not have: such an update is not applied by the
# launcher, the user gets a new download instead. Separate for each system — their builds differ. The Windows line
# keeps its exact form: launchers of old Windows builds look for it.
REQUIRES_RUNTIME = 1
REQUIRES_RUNTIME_MAC = 1
