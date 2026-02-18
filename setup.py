from setuptools import setup, find_packages

setup(
    name='web-traffic-bot',
    version='0.1',
    packages=find_packages(),
    install_requires=[
        'selenium',
        'pyyaml',
        'webdriver-manager',
    ],
    entry_points={
        'console_scripts': [
            'web-traffic-bot=your_module_name:main_function',
        ],
    },
)