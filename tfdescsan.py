#!/usr/bin/env python3
import sys
import csv
import logging
import hcl
from pprint import pprint

log_level = logging.DEBUG
logging.basicConfig(level=logging.WARN, format='%(asctime)s - %(levelname)s - %(message)s')
logging.getLogger('__main__').setLevel(log_level)
logging.getLogger('TFDesc').setLevel(log_level)
log = logging.getLogger(__name__)


def main(argv):
    tfd = TFDesc(argv[0], argv[1])
    tfd.parse_vars()


class TFDesc:
    """Read and validate terraform variable descriptions
    """
    def __init__(self, tsv_path, var_path):
        """Constructor

        :rtype: TFDesc
        :param tsv_path: Path to the tsv file containing the variable names and descriptions
        :param var_path: Path to the terraform variable.tf file
        """
        self.tsv_path = tsv_path
        self.var_path = var_path
        self.log = logging.getLogger(self.__class__.__name__)
        self.__vardesc = {}

    def __fill_vardesc(self):
        """Read the tsv file into memory
        """
        self.log.debug('Reading {} into memory'.format(self.tsv_path))
        with open(self.tsv_path, 'r') as tsvin:
            tsvin = csv.reader(tsvin, delimiter='\t')
            self.__vardesc = {
            r[0]: {'desc': r[1], 'gcp': self.__safe_list_get(r, 3, ''), 'aws': self.__safe_list_get(r, 2, ''),
                   'azure': self.__safe_list_get(r, 4, '')} for r in tsvin}

    @property
    def vardesc(self):
        """Access the variable description mapping

        :rtype: dict
        :return: variable description mapping
        """
        if len(self.__vardesc) == 0:
            self.__fill_vardesc()
        return self.__vardesc

    @staticmethod
    def __safe_list_get(l, idx, default):
        """Return an element from a list or if it doesn't exist a default value instead

        :param l: The list
        :param idx: Index of item in the list
        :param default: Default value to return if element at index doesn't exist
        """
        try:
            return l[idx]
        except IndexError:
            return default

    def parse_vars(self):
        """Parse the variables.tf file

        :rtype: bool
        :return: True or False
        """
        with open(self.var_path, 'r') as varin:
            variables = hcl.load(varin)
        for variable, data in variables['variable'].items():
            if 'description' not in data:
                self.log.error('Description missing for variable {}'.format(variable))
            else:
                if variable in self.vardesc:
                    description = self.vardesc[variable]['desc']
                    if data['description'] == description:
                        self.log.info('Variable {} is in a good state'.format(variable))
                    else:
                        self.log.warning(
                            "Variable {} with description \"{}\" doesn't match description mapping \"{}\"".format(
                                variable, data['description'], description))
                else:
                    self.log.error('Variable {} with description \"{}\" missing in description mapping'.format(variable, data['description']))


if __name__ == "__main__":
    main(sys.argv[1:])
