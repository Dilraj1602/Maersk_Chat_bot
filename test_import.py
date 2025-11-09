import sys
print('PYTHON:', sys.executable)
try:
    import backend.agent
    print('Imported backend.agent')
except Exception as e:
    import traceback
    traceback.print_exc()
    print('IMPORT FAILED:', e)
