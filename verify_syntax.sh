#!/bin/bash
# Save as: verify_syntax.sh

echo "🐍 Python Syntax Verification"
echo "=============================="

find . -name "*.py" -type f | while read file; do
    python3 -m py_compile "$file" 2>&1
    if [ $? -eq 0 ]; then
        echo "✅ $file"
    else
        echo "❌ SYNTAX ERROR: $file"
    fi
done

echo ""
echo "✅ Syntax check complete!"