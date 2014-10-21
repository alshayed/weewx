#
#    Copyright (c) 2009-2014 Tom Keffer <tkeffer@gmail.com>
#
#    See the file LICENSE.txt for your full rights.
#
#    $Revision$
#    $Author$
#    $Date$
#
"""Weather-specific stats"""

import weeutil.weeutil
import weecore.units
import weewx.wxformulas
import weecore.stats

# Import the weather-specific version of accum. This will cause weecore to
# become aware of their special properties.
import weewx.accum  # @UnusedImport

#===============================================================================
#                        Class WXDaySummaryArchive
#===============================================================================

class WXDaySummaryArchive(weecore.stats.DaySummaryArchive):
    """Daily summaries, suitable for WX applications.

    Like a regular stats database, except it understands wind, and heating- and cooling-degree days."""

    wx_sql_create_str = "CREATE TABLE day_wind (dateTime INTEGER NOT NULL UNIQUE PRIMARY KEY, "\
      "min REAL, mintime INTEGER, max REAL, maxtime INTEGER, sum REAL, count INTEGER, "\
      "wsum REAL, sumtime REAL, "\
      "max_dir REAL, xsum REAL, ysum REAL, dirsumtime INTEGER, squaresum REAL, wsquaresum REAL);"
                             
    def _initialize_day_tables(self, archiveSchema, cursor):
        """Specializing version that adds schema for wind data."""
        # First initialize my superclass:
        weecore.stats.DaySummaryArchive._initialize_day_tables(self, archiveSchema, cursor)
        
        # Now initialize the WX specific tables
        cursor.execute(WXDaySummaryArchive.wx_sql_create_str)
        
    # Default base temperature and unit type for heating and cooling degree days,
    # as a value tuple
    default_heatbase = (65.0, "degree_F", "group_temperature")
    default_coolbase = (65.0, "degree_F", "group_temperature")

    def getAggregate(self, timespan, obs_type, aggregateType, **option_dict):
        """Specialized version of getAggregate that can calculate heating or cooling degree days.

        timespan: An instance of weeutil.Timespan with the time period over which
        aggregation is to be done.

        obs_type: The observation type. For anything other than 'heatdeg' or 'cooldeg',
        the superclass is used.

        aggregateType: The type of aggregation to be done. Must be 'sum' or 'avg'.

        returns: A value tuple. First element is the aggregation value,
        or None if not enough data was available to calculate it, or if the aggregation
        type is unknown. The second element is the unit type (eg, 'degree_F').
        Third element is the unit group (always "group_temperature")."""

        # Check to see whether heating or cooling degree days are being asked for:
        if obs_type not in ['heatdeg', 'cooldeg']:
            # Use my superclass's version:
            return weecore.stats.DaySummaryArchive.getAggregate(self, timespan, obs_type, aggregateType, **option_dict)

        # Only summation (total) or average heating or cooling degree days is supported:
        if aggregateType not in ['sum', 'avg']:
            raise weewx.ViolatedPrecondition, "Aggregate type %s for %s not supported." % (aggregateType, obs_type)

        # Get the base for heating and cooling degree-days
        units_dict = option_dict['skin_dict'].get('Units', {})
        dd_dict = units_dict.get('DegreeDays', {})
        heatbase = dd_dict.get('heating_base', None)
        coolbase = dd_dict.get('cooling_base', None)
        heatbase_t = (float(heatbase[0]), heatbase[1], "group_temperature") if heatbase else WXDaySummaryArchive.default_heatbase
        coolbase_t = (float(coolbase[0]), coolbase[1], "group_temperature") if coolbase else WXDaySummaryArchive.default_coolbase

        _sum = 0.0
        _count = 0
        for daySpan in weeutil.weeutil.genDaySpans(timespan.start, timespan.stop):
            # Get the average temperature for the day as a value tuple:
            Tavg_t = weecore.stats.DaySummaryArchive.getAggregate(self, daySpan, 'outTemp', 'avg')
            # Make sure it's valid before including it in the aggregation:
            if Tavg_t is not None and Tavg_t[0] is not None:
                if obs_type == 'heatdeg':
                    # Convert average temperature to the same units as heatbase:
                    Tavg_target_t = weecore.units.convert(Tavg_t, heatbase_t[1])
                    _sum += weewx.wxformulas.heating_degrees(Tavg_target_t[0], heatbase_t[0])
                else:
                    # Convert average temperature to the same units as coolbase:
                    Tavg_target_t = weecore.units.convert(Tavg_t, coolbase_t[1])
                    _sum += weewx.wxformulas.cooling_degrees(Tavg_target_t[0], coolbase_t[0])
                _count += 1

        if aggregateType == 'sum':
            _result = _sum
        else:
            _result = _sum / _count if _count else None

        # Look up the unit type and group of the result:
        (t, g) = weecore.units.getStandardUnitType(self.std_unit_system, obs_type, aggregateType)
        # Return as a value tuple
        return weecore.units.ValueTuple(_result, t, g)

#===============================================================================
#                        function get_heat_cool
#===============================================================================

def get_heat_cool(statsdb, timespan, obs_type, aggregateType, heatbase_t, coolbase_t):
    """Calculate heating or cooling degree days for a given timespan.
    
    timespan: An instance of weeutil.Timespan with the time period over which
    aggregation is to be done.
    
    obs_type: One of 'heatdeg' or 'cooldeg'.
    
    aggregateType: The type of aggregation to be done. Must be 'sum' or 'avg'.
    
    heatbase_t, coolbase_t: Value tuples with the heating and cooling degree
    day base, respectively.
    
    returns: A value tuple. First element is the aggregation value,
    or None if not enough data was available to calculate it, or if the aggregation
    type is unknown. The second element is the unit type (eg, 'degree_F').
    Third element is the unit group (always "group_temperature")."""
    
    # The requested type must be heatdeg or cooldeg
    if weecore.debug:
        assert(obs_type in ['heatdeg', 'cooldeg'])

    # Only summation (total) or average heating or cooling degree days is supported:
    if aggregateType not in ['sum', 'avg']:
        raise weewx.ViolatedPrecondition, "Aggregate type %s for %s not supported." % (aggregateType, obs_type)

    _sum = 0.0
    _count = 0
    for daySpan in weeutil.weeutil.genDaySpans(timespan.start, timespan.stop):
        # Get the average temperature for the day as a value tuple:
        Tavg_t = statsdb.getAggregate(daySpan, 'outTemp', 'avg')
        # Make sure it's valid before including it in the aggregation:
        if Tavg_t is not None and Tavg_t[0] is not None:
            if obs_type == 'heatdeg':
                # Convert average temperature to the same units as heatbase:
                Tavg_target_t = weecore.units.convert(Tavg_t, heatbase_t[1])
                _sum += weewx.wxformulas.heating_degrees(Tavg_target_t[0], heatbase_t[0])
            else:
                # Convert average temperature to the same units as coolbase:
                Tavg_target_t = weecore.units.convert(Tavg_t, coolbase_t[1])
                _sum += weewx.wxformulas.cooling_degrees(Tavg_target_t[0], coolbase_t[0])
            _count += 1

    if aggregateType == 'sum':
        _result = _sum
    else:
        _result = _sum / _count if _count else None 

    # Look up the unit type and group of the result:
    (t, g) = weecore.units.getStandardUnitType(statsdb.std_unit_system, obs_type, aggregateType)
    # Return as a value tuple
    return weecore.units.ValueTuple(_result, t, g)
