#!/bin/bash

yq e 'explode(.)' ./tag.yaml.tmpl > ./tag.yaml
