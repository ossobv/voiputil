from setuptools import setup

setup(
    name='voiputil',
    version='0.1.0',
    py_modules=['monami', 'monamish'],
    entry_points='''
        [console_scripts]
        monami=monami:main
        monamish=monamish:main
    ''',
)
