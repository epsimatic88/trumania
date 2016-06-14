"""Base file for generator

"""
from datetime import datetime
import pandas as pd
import networkx as nx
from networkx.algorithms import bipartite
from random_generators import *
from clock import *
from actor import *
from relationship import *
from circus import *

import time


def main():
    """

    :rtype: None
    """
    ######################################
    # Define parameters
    ######################################
    tp = time.clock()
    print "Parameters"

    seed = 123456
    n_customers = 10000
    n_cells = 100
    prof = pd.Series([5., 5., 5., 5., 5., 3., 3.],
                     index=[timedelta(days=x, hours=23, minutes=59, seconds=59) for x in range(7)])
    time_step = 3600

    mov_prof = pd.Series(
        [1., 1., 1., 1., 1., 1., 1., 1., 5., 10., 5., 1., 1., 1., 1., 1., 1., 5., 10., 5., 1., 1., 1., 1.],
        index=[timedelta(hours=h, minutes=59, seconds=59) for h in range(24)])

    cells = ["CELL_%s" % (str(i).zfill(4)) for i in range(n_cells)]

    print "Done"
    ######################################
    # Define clocks
    ######################################
    tc = time.clock()
    print "Clock"
    the_clock = Clock(datetime(year=2016, month=6, day=8), time_step, "%d%m%Y %H:%M:%S", seed)
    print "Done"
    ######################################
    # Define generators
    ######################################
    tg = time.clock()
    print "Generators"
    msisdn_gen = MSISDNGenerator("msisdn-test-1", "0032", ["472", "473", "475", "476", "477", "478", "479"], 6, seed)
    activity_gen = GenericGenerator("user-activity", "pareto", {"a": 1.2, "m": 10.}, seed)
    timegen = WeekProfiler(time_step, prof, seed)

    mobilitytimegen = DayProfiler(time_step, mov_prof, seed)
    networkchooser = WeightedChooserAggregator("B", "weight", seed)
    networkweightgenerator = GenericGenerator("network-weight", "pareto", {"a": 1.2, "m": 1.}, seed)

    mobilitychooser = WeightedChooserAggregator("CELL", "weight", seed)
    mobilityweightgenerator = GenericGenerator("mobility-weight", "exponential", {"scale": 1.})

    init_mobility_generator = GenericGenerator("init-mobility", "choice", {"a": cells})
    print "Done"
    ######################################
    # Initialise generators
    ######################################
    tig = time.clock()
    print "initialise Time Generators"
    timegen.initialise(the_clock)
    mobilitytimegen.initialise(the_clock)
    print "Done"
    ######################################
    # Define Actors, Relationships, ...
    ######################################
    tcal = time.clock()
    print "Create callers"
    customers = CallerActor(n_customers)
    print "Done"
    tatt = time.clock()
    customers.add_attribute("MSISDN", msisdn_gen)
    customers.update_attribute("activity", activity_gen)
    customers.update_attribute("clock", timegen, weight_field="activity")

    print "Added atributes"
    tsna = time.clock()
    print "Creating social network"
    social_network = pd.DataFrame.from_records(nx.fast_gnp_random_graph(n_customers, 0.4, seed).edges(),
                                             columns=["A", "B"])
    tsnaatt = time.clock()
    print "Done"
    network = WeightedRelationship("A", "B", networkchooser)
    network.add_relation("A", social_network["A"].values, "B", social_network["B"].values,
                         networkweightgenerator.generate(len(social_network.index)))
    network.add_relation("A", social_network["B"].values, "B", social_network["A"].values,
                         networkweightgenerator.generate(len(social_network.index)))
    print "Done SNA"
    tmo = time.clock()
    print "Mobility"
    mobility_df = pd.DataFrame.from_records(
        [(e[0], cells[e[1]]) for e in make_random_bipartite_data(n_customers, n_cells, 0.4, seed)],
        columns=["A", "CELL"])
    print "Network created"
    tmoatt = time.clock()
    mobility = WeightedRelationship("A", "CELL", mobilitychooser)
    mobility.add_relation("A", mobility_df["A"], "CELL", mobility_df["CELL"],
                          mobilityweightgenerator.generate(len(mobility_df.index)))

    customers.add_transient_attribute("CELL", init_mobility_generator, mobilitytimegen)
    print "Done all customers"
    ######################################
    # Create circus
    ######################################
    tci = time.clock()
    print "Creating circus"
    flying = Circus(the_clock)
    flying.add_actor("customers", customers)
    flying.add_relationship("A", "B", network)
    flying.add_generator("time", timegen)
    flying.add_generator("networkchooser", networkchooser)

    flying.add_action("customers",
                      "make_calls",
                      {"new_time_generator": timegen, "relationship": network},
                      {"timestamp": True,
                       "join": [("A", customers, "MSISDN", "A_NUMBER"),
                                ("B", customers, "MSISDN", "B_NUMBER"),
                                ("A", customers, "CELL", "CELL_A"),
                                ("B", customers, "CELL", "CELL_B"),]})
    flying.add_action("customers",
                      "make_attribute_action",
                      {"attr_name": "CELL", "params": {"new_time_generator": mobilitytimegen,
                                                       "relationship": mobility,
                                                       "id1": "A",
                                                       "id2": "CELL"}},
                      {"timestamp": True})

    flying.add_increment(timegen)
    print "Done"
    ######################################
    # Run
    ######################################
    tr = time.clock()
    print "Start run"
    all_cdrs = []
    all_mov = []
    for i in range(100):
        print "iteration %s on %s" % (i,100)
        all_data = flying.one_round()
        # print len(these_cdrs.index), "CDRs generated"
        all_cdrs.append(all_data[0])
        all_mov.append(all_data[1])
        print '\r'
    tf = time.clock()

    all_times = [tp,tc,tg,tig,tcal,tsna,tsnaatt,tmo, tmoatt,tci,tr,tf]

    return (flying, pd.concat(all_cdrs, ignore_index=True),pd.concat(all_mov,ignore_index=True),all_times)


def make_random_bipartite_data(n1, n2, p, seed):
    mobility_network = bipartite.random_graph(n1, n2, 0.4, seed)
    i1 = 0
    i2 = 0
    node_index = {}
    node_type = {}
    for n, d in mobility_network.nodes(data=True):
        if d["bipartite"] == 0:
            node_index[n] = i1
            i1 += 1
        else:
            node_index[n] = i2
            i2 += 1
        node_type[n] = d["bipartite"]
    edges_for_out = []
    for e in mobility_network.edges():
        if node_type[e[0]] == 0:
            edges_for_out.append((node_index[e[0]], node_index[e[1]]))
        else:

            edges_for_out.append((node_index[e[1]], node_index[e[2]]))
    return edges_for_out


if __name__ == "__main__":
    main()
