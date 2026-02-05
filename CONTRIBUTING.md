# Contributing to NeuroSurveillance System

Thank you for your interest in contributing! This document provides guidelines for contributing to this project.

## How to Contribute

### Reporting Issues

1. **Search existing issues** to avoid duplicates
2. **Use the issue template** if available
3. **Include relevant information:**
   - Hardware (Pi model, NVR specs)
   - Software versions (OS, Docker, Frigate)
   - Configuration files (sanitize sensitive data!)
   - Error messages and logs
   - Steps to reproduce

### Suggesting Enhancements

1. **Check existing issues** for similar suggestions
2. **Describe the use case** - why is this needed?
3. **Propose a solution** if you have one
4. **Consider backward compatibility**

### Pull Requests

1. **Fork the repository**
2. **Create a feature branch:** `git checkout -b feature/your-feature`
3. **Make your changes**
4. **Test thoroughly**
5. **Update documentation** if needed
6. **Submit a pull request**

## Code Guidelines

### Configuration Files

- Use clear comments explaining each section
- Mark all user-configurable values as `{VARIABLES}`
- Include example values in comments
- Document any gotchas or warnings

### Scripts

- Use `#!/bin/bash` shebang
- Include header comment explaining purpose
- Add error handling (`set -euo pipefail`)
- Use meaningful variable names
- Add installation instructions in comments

### Documentation

- Use clear, concise language
- Include code examples
- Add table of contents for long documents
- Test all commands before documenting

## Testing

Before submitting:

1. **Test on actual hardware** if possible
2. **Verify all `{VARIABLES}` are documented**
3. **Run the validation script**
4. **Check for typos and formatting**

## Security

- **Never commit real IP addresses or credentials**
- **Use placeholders** for all sensitive values
- **Review for exposed secrets** before submitting

## Code of Conduct

- Be respectful and constructive
- Welcome newcomers
- Focus on the issue, not the person
- Accept feedback gracefully

## Questions?

Open an issue with the "question" label if you need clarification.

Thank you for contributing!
