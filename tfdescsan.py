#!/usr/bin/env python3
import os
import io
import sys
import re
import csv
import tempfile
import logging
import argparse
try:
    import hcl
except ImportError:
    print('Error: Python hcl module missing!\nTry installing via:\n  $ pip install pyhcl')
    print('HCL is the HashiCorp configuration language.\nSee https://github.com/hashicorp/hcl for details.')
    sys.exit(2)


def main(argv):
    p = argparse.ArgumentParser(description='Parse terraform variables.tf and update variable descriptions')
    p.add_argument('--tsv', '-t', help='TSV description mapping file', dest='tsv_path', required=True)
    p.add_argument('--var', '-f', help='Terraform variables.tf file', dest='var_path', required=True)
    pg = p.add_mutually_exclusive_group()
    pg.add_argument('--out', '-o', help='Output variables.tf file', dest='out_path', type=str)
    pg.add_argument('--inplace', '-i', help='Replace variables.tf in place', dest='inplace', action='store_true',
                    default=False)
    p.add_argument('--cloud', '-c', help='Name of Cloud', dest='cloud', choices=['aws', 'gcp', 'azure'])
    p.add_argument('--verbose', '-v', help='Verbose logging', dest='verbose', action='store_true', default=False)
    args = p.parse_args(argv)

    # set up logging
    log_level = logging.INFO
    if args.verbose:
        log_level = logging.DEBUG

    root = logging.getLogger()
    root.setLevel(logging.DEBUG)
    ch = logging.StreamHandler(sys.stderr)
    ch.setLevel(log_level)
    formatter = logging.Formatter('%(asctime)s - %(levelname)s - %(message)s')
    ch.setFormatter(formatter)
    root.addHandler(ch)

    # do the work
    tfd = TFVarDesc(args.tsv_path, args.var_path, args.cloud)
    missing = Missing()
    tfd.register_mapping_missing_callback(missing.callback)

    if args.out_path or args.inplace:
        # write the updated variables to either a new file or replace in-place
        # if the later we add a flag that tells the method to only replace
        # if content has changed
        out_path = args.var_path if args.inplace else args.out_path
        tfd.write_updated_variables(out_path, args.inplace)
    else:
        print(tfd.updated_variables)  # dump the updated variables.tf to stdout

    missing.process()  # do something with the list of missing variables

    sys.exit(0)  # explicit exit for readability


class Missing:
    """Example of a class that implements the mapping_missing callback
    and collects missing variables.
    """
    def __init__(self):
        self.data = []

    def callback(self, variable):
        self.data.append(variable)

    def process(self):
        # todo: do something with the data we collected - e.g. notify on Slack or send an Email
        return


class TFVarDesc:
    """Read and validate terraform variable descriptions
    """
    def __init__(self, tsv_path, var_path, cloud=None):
        """Constructor

        :rtype: TFVarDesc
        :param tsv_path: Path to the tsv file containing the variable names and descriptions
        :param var_path: Path to the terraform variable.tf file
        :param cloud: Name of the cloud we're generating descriptions for
        :return: TFVarDesc object
        """
        self._tsv_path = tsv_path
        self._var_path = var_path
        self._cloud = cloud
        self._log = logging.getLogger(self.__class__.__name__)
        self.__vardesc = {}
        self._plan = {}
        self.__mapping_missing_callbacks = []
        self.__variables = None
        self.__updated_variables = None

    def __repr__(self):
        return self.updated_variables

    def __hash__(self):
        return hash(self.updated_variables)

    def __eq__(self, other):
        return self.updated_variables == other.updated_variables

    def __fill_vardesc(self):
        """Read the tsv file into memory
        """
        if self._tsv_path.startswith('http://') or self._tsv_path.startswith('https://'):
            self._log.debug('Loading {} from network into memory'.format(self._tsv_path))
            try:
                import requests
            except ImportError:
                error_msg = 'Error: Python requests module missing! Try installing via: $ pip install requests'
                self._log.fatal(error_msg)
                raise RuntimeError(error_msg)
            tsv_data = requests.get(self._tsv_path).text
            tsv_in = io.StringIO(tsv_data)
        else:
            self._log.debug('Loading {} from disk into memory'.format(self._tsv_path))
            tsv_in = open(self._tsv_path, 'r')
        tsv = csv.reader(tsv_in, delimiter='\t')
        self.__vardesc = {
        r[0]: {'desc': r[1], 'gcp': self.__safe_list_get(r, 3, ''), 'aws': self.__safe_list_get(r, 2, ''),
               'azure': self.__safe_list_get(r, 4, '')} for r in tsv if r[1].lower() != 'description'}
        tsv_in.close()

    @property
    def vardesc(self):
        """Return the variable description mapping

        :rtype: dict
        :return: variable description mapping
        """
        if len(self.__vardesc) == 0:
            self.__fill_vardesc()
        return self.__vardesc

    @property
    def variables(self):
        """Return the variables.tf file as a string.
        Read it from disk if required.
        """
        if self.__variables is None:
            self._log.debug('Loading {} into memory'.format(self._var_path))
            with open(self._var_path, 'r') as varin:
                self.__variables = varin.read()
        return self.__variables

    @property
    def updated_variables(self):
        """Return the updated variables.tf file as a string.
        Parse and update the original if required.
        """
        if self.__updated_variables is None:
            self.__parse_vars()
            self.__execute_plan()
        return self.__updated_variables

    @property
    def variables_io(self):
        """Return an I/O object for our variables.tf file
        """
        return io.StringIO(self.variables)

    @property
    def updated_variables_io(self):
        """Return an I/O object for our updated variables.tf file
        """
        return io.StringIO(self.updated_variables)

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

    def __parse_vars(self):
        """Parse the variables.tf file

        :rtype: bool
        :return: True or False
        """
        hcl_data = hcl.load(self.variables_io)
        if 'variable' in hcl_data:
            var_key = 'variable'
        elif 'output' in hcl_data:
            var_key = 'output'
        else:
            error_msg = 'Found neither "variable" nor "output" in hcl file'
            self._log.fatal(error_msg)
            raise RuntimeError(error_msg)

        for variable, data in hcl_data[var_key].items():

            description = None
            if variable in self.vardesc:
                description = self.vardesc[variable]['desc']
                if self._cloud in self.vardesc[variable] and len(self.vardesc[variable][self._cloud]) > 0:
                    description += ' {}'.format(self.vardesc[variable][self._cloud])
            else:
                self.__on_mapping_missing(variable)

            if 'description' not in data:
                self._log.error('Description missing for variable {}'.format(variable))
                if description:
                    self.__update_plan(variable, 'insert', description)
                else:
                    self._log.warning('Variable {} also missing in description mapping'.format(variable))
            else:
                if data['description'] == description:
                    self._log.debug('Variable {} is in a good state'.format(variable))
                else:
                    if description:
                        self._log.warning(
                            "Variable {} with description \"{}\" doesn't match description mapping \"{}\"".format(
                                variable, data['description'], description))
                        self.__update_plan(variable, 'update', description)
                    else:
                        self._log.warning(
                            'Variable {} with description \"{}\" missing in description mapping'.format(variable, data[
                                'description']))

    def __update_plan(self, variable, operation, description):
        """Update the plan that leads to an updated variables.tf

        :rtype: bool
        :param variable: Name of the variable that we're planing to update
        :param operation: Either 'insert' or 'update' depending on whether or not a description already exists
        :param description: The description text itself
        :return: True or False
        """
        if variable in self._plan:
            self._log.error('Variable {} already exists in plan'.format(variable))
            return False

        self._log.debug('Updating plan for {}'.format(variable))
        self._plan[variable] = {'op': operation, 'desc': description}
        return True

    def __execute_plan(self):
        """Execute the planned modifications and create the updated variables.tf
        """
        self._log.debug('Executing plan')
        updated_variables = []
        update_next_description = False
        current_variable = None
        current_variables = self.variables_io.readlines()
        p = re.compile(r'(variable|output)\s+"(?P<variable>.*?)"')  # todo: can variables be defined in single quotes?
        idx = 0
        close = False
        while idx < len(current_variables):  # we're using manual iteration because we might want to skip some lines
            line = current_variables[idx]
            idx += 1
            m = p.search(line)
            if m:  # if the current line defines a variable
                current_variable = m.group('variable')
                self._log.debug('Found variable {} in line {}'.format(current_variable, idx+1))
                if current_variable in self._plan:
                    self._log.debug('Executing {} on {} with description "{}"'.format(self._plan[current_variable]['op'],
                                                                                   current_variable,
                                                                                   self._plan[current_variable][
                                                                                       'desc']))
                    if self._plan[current_variable]['op'] == 'insert':  # if we're adding a missing description
                        # we want to maintain the user's style so we look ahead to see how many
                        # whitespaces they've been using in the rest of the variable definition
                        ws = self.__whitespaces(current_variables, idx)
                        description = '{}description = "{}"\n'.format(ws, self._plan[current_variable]['desc'])
                        # if the variable definition was empty and closed on the same line as the description
                        if '}' in line:
                            line = line.replace('}', '')  # remove the closing bracket
                            close = True  # and set a flag that tells us to close after we added the description
                        updated_variables.append(line)
                        # if the opening bracket is on the next line instead of the one that defines the variable
                        if '{' not in line and '{' in current_variables[idx]:
                            updated_variables.append(current_variables[idx])  # append the next line
                            idx += 1                                          # and skip to the one after
                        updated_variables.append(description)
                        if close:                            # if we're supposed to close the variable definition
                            updated_variables.append('}\n')  # add the closing bracket
                            close = False                    # and reset the flag
                        current_variable = None
                        continue
                    elif self._plan[current_variable]['op'] == 'update':  # if we're updating a wrong description
                        # we set a flag that tells us to update the next description we encounter
                        update_next_description = True
            # todo: maybe use a regex instead of just looking for the string 'description'
            if update_next_description and 'description' in line:
                line = re.sub('^(.*description\s?=\s?")(.*?)(".*)', '\\1{}\\3'.format(self._plan[current_variable]['desc']), line)
                update_next_description = False
                current_variable = None
            updated_variables.append(line)
        self.__updated_variables = ''.join(updated_variables)

    def __on_mapping_missing(self, variable):
        """Event handler that's being called whenever a variable
        is missing from the description mappings file.

        :param variable: Name of the variable that's missing from the description mapping
        """
        for callback in self.__mapping_missing_callbacks:
            self._log.debug('Callback {}'.format(callback))
            callback(variable)

    def register_mapping_missing_callback(self, callback):
        """Register event handlers that's being called back whenever we encounter
        a variable in a variables.tf file that's missing from the description mapping.

        :param callback: A function that will be called if a variable is missing from the description mapping
        """
        self.__mapping_missing_callbacks.append(callback)

    @staticmethod
    def __whitespaces(l, i, search_lines=3):
        """Search the values of a list for leading whitespaces in the next couple of lines
        starting with index i.

        :rtype: str
        :param l: List to search for leading whitespaces
        :param i: Index from where to start searching
        :param search_lines: Maximum number of lines to search from index
        :return: Some number of whitespaces (tabs or spaces)
        """
        p = re.compile(r'^(?P<whitespace>[\t ]+)')
        for x in range(i, i+search_lines):
            if x < len(l):
                m = p.search(l[x])
                if m:
                    return m.group('whitespace')
        return '  '

    def write_updated_variables(self, out_path, on_change=False):
        """Write the updated variables to a file.

        :param out_path: Path to file where we should write the updated variables to
        :param on_change: Only write the file if we updated the variables
        """
        if on_change and self.variables == self.updated_variables:
            self._log.debug("Variables haven't changed - skipping write")
            return
        dirname, basename = os.path.split(out_path)
        temp = tempfile.NamedTemporaryFile(prefix=basename, dir=dirname, delete=False)
        self._log.debug('Writing updated variables to {}'.format(temp.name))
        temp.write(self.updated_variables.encode())
        temp.close()
        self._log.debug('Moving {} to {}'.format(temp.name, out_path))
        os.rename(temp.name, out_path)


if __name__ == "__main__":
    main(sys.argv[1:])
