"""Project release numbering: carry the third component after nine."""
import re

def next_version(current):
    if not re.fullmatch(r'\d+\.\d+\.\d+',current):raise ValueError('Expected major.minor.patch')
    major,minor,patch=map(int,current.split('.'))
    return f'{major}.{minor+1}.0' if patch>=9 else f'{major}.{minor}.{patch+1}'

def validate_new_version(version):
    if not re.fullmatch(r'\d+\.\d+\.[0-9]',version):raise ValueError('New release patch must be 0–9')
    return version

if __name__=='__main__':
    import sys
    print(next_version(sys.argv[1]))
