#!/bin/bash

yq e 'explode(.)' ./tag.tmpl > ./tag.yaml
