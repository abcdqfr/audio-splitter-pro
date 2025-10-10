#!/bin/bash

# Create a temporary xdg-settings wrapper
TEMP_DIR=$(mktemp -d)
XDG_WRAPPER="$TEMP_DIR/xdg-settings"

cat > "$XDG_WRAPPER" << 'EOF'
#!/bin/bash
# Minimal xdg-settings wrapper for FreeTube
case "$1" in
    "get"|"set"|"check")
        # Return success for most operations
        exit 0
        ;;
    *)
        # Default success
        exit 0
        ;;
esac
EOF

chmod +x "$XDG_WRAPPER"

# Add the temp directory to PATH and run FreeTube
export PATH="$TEMP_DIR:$PATH"
flatpak run io.freetubeapp.FreeTube "$@"

# Cleanup
rm -rf "$TEMP_DIR"

