#!/usr/bin/env python

import taskflow.engines
from taskflow.patterns import linear_flow as lt
from taskflow import task
from taskflow.types import failure as task_failed


class CallJim(task.Task):


    default_provides = set(['jim_new_number'])

    def execute(self, jim_number, *args, **kwargs):
        print "Calling Jim %s." % jim_number
        jim_new_number = jim_number + '123'

        return {'jim_new_number': jim_new_number}

    def revert(self, result, *args, **kwargs):
        if isinstance(result, task_failed.Failure):
            return None

        jim_new_number = result['jim_new_number']
        print "Call %s and apologizing." % jim_new_number


class CallJoe(task.Task):

    default_provides = set(['joe_new_number', 'jim_new_number'])

    def execute(self, joe_number, jim_new_number, *args, **kwargs):
        print "Calling jim %s." % jim_new_number
        print "Calling Joe %s." % joe_number
        joe_new_number = joe_number + '123'

        return {'jim_new_number': jim_new_number,
                'joe_new_number': joe_new_number}

    def revert(self, result, *args, **kwargs):
        if isinstance(result, task_failed.Failure):
            return None

        jim_new_number = result['jim_new_number']
        joe_new_number = result['joe_new_number']

        print "Calling %s and apologizing." % jim_new_number
        print "Calling %s and apologizing." % joe_new_number


class CallJmilkFan(task.Task):

    default_provides = set(['new_numbers'])

    def execute(self, jim_new_number, joe_new_number, jmilkfan_number,
                *args, **kwargs):
        raise ValueError('Error')
        print "Calling jim %s" % jim_new_number
        print "Calling joe %s" % joe_new_number
        print "Calling jmilkfan %s" % jmilkfan_number
        jmilkfan_new_number = jmilkfan_number + '123'

        new_numbers =  {'jim_new_number': jim_new_number,
                        'joe_new_number': joe_new_number,
                        'jmilkfan_new_number': jmilkfan_new_number}

        return {'new_numbers': new_numbers}

    def revert(self, result, *args, **kwargs):
        if isinstance(result, task_failed.Failure):
            return None

        jim_new_number = result['jim_new_number']
        joe_new_number = result['joe_new_number']
        jmilkfan_new_number = result['jmilkfan_new_number']

        print "Calling %s and apologizing." % jim_new_number
        print "Calling %s and apologizing." % joe_new_number
        print "Calling %s and apologizing." % jmilkfan_new_number


def get_flow(flow, numbers):
    flow_name = flow
    flow_api = lt.Flow(flow_name)

    flow_api.add(CallJim(),
                 CallJoe(),
                 CallJmilkFan())

    return taskflow.engines.load(flow_api,
                                 engine_conf={'engine': 'serial'},
                                 store=numbers)

def main():
    numbers = {'jim_number': '1'*6,
               'joe_number': '2'*6,
               'jmilkfan_number': '3'*6}
    try:
        flow_engine = get_flow(flow='taskflow-demo',
                               numbers=numbers)

        flow_engine.run()
    except Exception:
        print "TaskFlow Failed!"
        raise

    new_numbers = flow_engine.storage.fetch('new_numbers')


if __name__ == '__main__':
    main()
