#!/bin/bash
SRC=/home/user/andre-assassin

# Core documentation we built
cp $SRC/README.md .
cp $SRC/QUICK_START.md .
cp $SRC/CONTRIBUTING.md .
cp $SRC/CODE_OF_CONDUCT.md .
cp $SRC/CHANGELOG.md .
cp $SRC/RELEASE_NOTES_v0.1.md .
cp $SRC/install.sh .

# Configuration
cp $SRC/.env.example .
cp $SRC/requirements.txt .
cp $SRC/docker-compose.yml .
cp $SRC/.gitignore .
cp $SRC/.dockerignore .

# Application code
cp -r $SRC/app .

# CI/CD
cp -r $SRC/.github .

# Documentation
mkdir -p docs
cp $SRC/docs/multi_objective_optimization_guide.md docs/

# Database
mkdir -p migrations
cp $SRC/migrations/create_complete_schema.sql migrations/

# Demo
cp $SRC/demo_multi_objective.py .

echo "✅ Clean files copied"
