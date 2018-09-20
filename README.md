# Terraform variable description sanitizer

## Intro
When working with many terraform modules that are using the same input and output variables their descriptions can diverge quickly. This little helper takes a tsv (tab-separated values) file containing variable to description mappings and validates/updates `variables.tf` files against them. It tries to maintain the original formating of the file.

There's also a `--cloud` argument that's mainly useful for our specific use case where we have terraform modules for different clouds. This allows to append cloud specific strings to the generic description. It's entirely optional and can be omitted (both on the cli and in the tsv mapping table).

The format of the variable description mapping table is

| Variable | Description | AWS appendix | GCP appendix | Azure appendix |
|----------|-------------|--------------|--------------|----------------|
| `region` | `Region to deploy instance in` | `(e.g. us-west-2)` | `(e.g. us-west1)` | `(e.g. East US)` |

## Usage
```
usage: tfdescsan.py [-h] --tsv TSV_PATH --var VAR_PATH
                    [--out OUT_PATH | --inplace | --test]
                    [--cloud {aws,gcp,azure}] [--verbose]

Parse terraform variables.tf and update variable descriptions

optional arguments:
  -h, --help            show this help message and exit
  --tsv TSV_PATH, -m TSV_PATH
                        TSV description mapping file
  --var VAR_PATH, -f VAR_PATH
                        Terraform variables.tf file
  --out OUT_PATH, -o OUT_PATH
                        Output variables.tf file
  --inplace, -i         Replace variables.tf in place
  --test, -t            Test only - exit > 0 on errors or warnings
  --cloud {aws,gcp,azure}, -c {aws,gcp,azure}
                        Name of Cloud
  --verbose, -v         Verbose logging
```

## Docker
An automated Docker build is available as `lloesche/tfdescsan`
