#!/usr/bin/env python
# -*- coding: UTF-8 -*-
import my_rasa

if __name__ == '__main__':

    my_rasa.train(
        domain="domain.yml",
        config="config.yml",
        output="models",
        training_files="data"
    )
