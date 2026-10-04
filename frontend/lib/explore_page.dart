// ignore_for_file: unused_local_variable
import 'dart:async';
import 'dart:convert';
import 'dart:math' as math;
import 'package:flutter/material.dart';
import 'package:flutter_map/flutter_map.dart';
import 'package:http/http.dart' as http;
import 'package:latlong2/latlong.dart';
import 'package:geolocator/geolocator.dart';

class ExplorePage extends StatefulWidget {
  final double? latitude;
  final double? longitude;

  const ExplorePage({super.key, this.latitude, this.longitude});

  @override
  State<ExplorePage> createState() => _ExplorePageState();
}

class _ExplorePageState extends State<ExplorePage> {
  final MapController _mapController = MapController();

  // ============================================================
  // API
  // ============================================================

  static const String apiBaseUrl = 'https://marineintelligence.onrender.com';
  // ============================================================
  // DEFAULT LOCATION
  // ============================================================

  static const LatLng defaultLocation = LatLng(18.5204, 73.8567);

  // ============================================================
  // MARINE ANALYSIS LOCATIONS
  // ============================================================

  static const List<LatLng> marinePoints = [
    LatLng(18.80, 72.50),
    LatLng(20.29, 71.02),
    LatLng(18.70, 72.70),
    LatLng(16.95, 73.20),
    LatLng(15.90, 73.55),
    LatLng(14.50, 73.60),
  ];

  // ============================================================
  // CURRENT LOCATION
  // ============================================================

  LatLng get currentLocation {
    if (livePosition != null) {
      return LatLng(livePosition!.latitude, livePosition!.longitude);
    }

    if (widget.latitude != null && widget.longitude != null) {
      return LatLng(widget.latitude!, widget.longitude!);
    }

    return defaultLocation;
  }

  // ============================================================
  // LAYER SETTINGS
  // ============================================================

  bool showChlorophyll = true;
  bool showSST = false;
  bool showPFZ = true;
  bool showRisk = true;
  bool showSafeZones = false;
  LatLng? geofenceAnchor;
  double geofenceSpeedKmh = 0.0;

  // ============================================================
  // CHLOROPHYLL DATA
  // ============================================================

  List<Map<String, dynamic>> chlorophyllPoints = [];
  List<Map<String, dynamic>> hotspotData = [];

  double? minChlorophyll;
  double? maxChlorophyll;
  double? chlorophyllThreshold;

  // ============================================================
  // SST DATA
  // ============================================================

  List<Map<String, dynamic>> sstPoints = [];

  double? minSST;
  double? maxSST;

  String sstStatus = 'SST not loaded';

  // ============================================================
  // PFZ DATA
  // ============================================================

  List<Map<String, dynamic>> pfzPoints = [];

  int pfzTotal = 0;
  int pfzHigh = 0;
  int pfzModerate = 0;
  int pfzLow = 0;

  String pfzStatus = 'Fishing potential not loaded';

  double? selectedPFZScore;
  String? selectedPFZLevel;

  // ============================================================
  // GENERAL STATUS
  // ============================================================

  bool satelliteLoading = false;

  String satelliteStatus = 'Loading marine satellite data...';

  // ============================================================
  // INIT
  // ============================================================
  Position? livePosition;
  StreamSubscription<Position>? positionSubscription;
  bool locationLoading = true;
  Future<void> _startLiveLocation() async {
    try {
      bool serviceEnabled = await Geolocator.isLocationServiceEnabled();

      if (!serviceEnabled) {
        if (mounted) {
          setState(() {
            locationLoading = false;
          });
        }
        return;
      }

      LocationPermission permission = await Geolocator.checkPermission();

      if (permission == LocationPermission.denied) {
        permission = await Geolocator.requestPermission();
      }

      if (permission == LocationPermission.denied ||
          permission == LocationPermission.deniedForever) {
        if (mounted) {
          setState(() {
            locationLoading = false;
          });
        }
        return;
      }

      final initialPosition = await Geolocator.getCurrentPosition();

      if (mounted) {
        setState(() {
          livePosition = initialPosition;
          locationLoading = false;
        });
      }

      positionSubscription =
          Geolocator.getPositionStream(
            locationSettings: const LocationSettings(
              accuracy: LocationAccuracy.high,
              distanceFilter: 5,
            ),
          ).listen((Position position) {
            if (!mounted) return;

            setState(() {
              livePosition = position;

              geofenceSpeedKmh = position.speed * 3.6;

              geofenceAnchor ??= LatLng(position.latitude, position.longitude);
            });
          });
    } catch (e) {
      if (mounted) {
        setState(() {
          locationLoading = false;
        });
      }
    }
  }

  @override
  void initState() {
    super.initState();

    _loadAllMarineData();
    _startLiveLocation();
  }

  // ============================================================
  // DISTANCE
  // ============================================================

  double _distanceSquared(LatLng a, LatLng b) {
    final dLat = a.latitude - b.latitude;
    final dLon = a.longitude - b.longitude;

    return dLat * dLat + dLon * dLon;
  }

  // ============================================================
  // SORT MARINE LOCATIONS
  // ============================================================

  List<LatLng> _sortedMarinePoints() {
    final user = currentLocation;

    final points = List<LatLng>.from(marinePoints);

    points.sort((a, b) {
      return _distanceSquared(user, a).compareTo(_distanceSquared(user, b));
    });

    return points;
  }

  // ============================================================
  // SAFE API CALL
  // ============================================================

  Future<Map<String, dynamic>?> _safeRequest(
    Future<Map<String, dynamic>> Function() request,
  ) async {
    try {
      final result = await request();
      debugPrint('MARINE API SUCCESS');
      return result;
    } catch (e) {
      debugPrint('MARINE API ERROR: $e');
      return null;
    }
  }

  // ============================================================
  // LOAD ALL MARINE DATA
  // ============================================================

  Future<void> _loadAllMarineData() async {
    if (!mounted) return;

    setState(() {
      satelliteLoading = true;
      satelliteStatus = 'Finding marine satellite region...';
      pfzStatus = 'Loading fishing potential...';

      // Clear old map data before fresh request.
      chlorophyllPoints = [];
      hotspotData = [];
      sstPoints = [];
      pfzPoints = [];

      pfzTotal = 0;
      pfzHigh = 0;
      pfzModerate = 0;
      pfzLow = 0;

      minChlorophyll = null;
      maxChlorophyll = null;
      chlorophyllThreshold = null;

      minSST = null;
      maxSST = null;
    });

    final candidates = _sortedMarinePoints();

    LatLng? successfulMarinePoint;

    bool gotAnyData = false;
    bool gotPFZ = false;
    bool gotChlorophyll = false;
    bool gotSST = false;

    for (final marinePoint in candidates) {
      if (!mounted) return;

      setState(() {
        satelliteStatus =
            'Loading marine data near '
            '${marinePoint.latitude.toStringAsFixed(2)}, '
            '${marinePoint.longitude.toStringAsFixed(2)}...';
      });

      /*
       * IMPORTANT:
       *
       * Each API is handled independently.
       *
       * Earlier:
       * Future.wait()
       *
       * If PFZ failed, SST/Chlorophyll also got discarded.
       *
       * Now:
       * PFZ / SST / Chlorophyll can succeed independently.
       */

      final chlorophyllFuture = _safeRequest(
        () => _requestChlorophyll(marinePoint.latitude, marinePoint.longitude),
      );

      final sstFuture = _safeRequest(
        () => _requestSST(marinePoint.latitude, marinePoint.longitude),
      );

      final pfzFuture = _safeRequest(
        () => _requestPFZ(marinePoint.latitude, marinePoint.longitude),
      );

      final chlorophyll = await chlorophyllFuture;
      final sst = await sstFuture;
      final pfz = await pfzFuture;

      // ========================================================
      // CHLOROPHYLL
      // ========================================================

      if (chlorophyll != null) {
        final raw = chlorophyll['points'];

        final hasData =
            chlorophyll['status'] == 'ok' && raw is List && raw.isNotEmpty;

        if (hasData) {
          _applyChlorophyllData(chlorophyll);

          gotChlorophyll = true;
          gotAnyData = true;
        }
      }

      // ========================================================
      // SST
      // ========================================================

      if (sst != null) {
        final raw = sst['points'];

        final hasData = sst['status'] == 'ok' && raw is List && raw.isNotEmpty;

        if (hasData) {
          _applySSTData(sst);

          gotSST = true;
          gotAnyData = true;
        }
      }

      // ========================================================
      // PFZ
      // ========================================================

      if (pfz != null) {
        final raw = pfz['points'];

        final hasData = pfz['status'] == 'ok' && raw is List && raw.isNotEmpty;

        if (hasData) {
          _applyPFZData(pfz);

          gotPFZ = true;
          gotAnyData = true;
        }
      }

      // ========================================================
      // IF THIS REGION GAVE DATA
      // ========================================================

      if (gotAnyData) {
        successfulMarinePoint = marinePoint;

        break;
      }
    }

    if (!mounted) return;

    // ==========================================================
    // FINAL STATUS
    // ==========================================================

    if (successfulMarinePoint != null) {
      _mapController.move(successfulMarinePoint, 6.8);

      String status;

      if (gotPFZ && gotChlorophyll && gotSST) {
        status = 'Live marine data updated';
      } else if (gotPFZ) {
        status = 'Live PFZ + satellite data updated';
      } else if (gotChlorophyll && gotSST) {
        status = 'Live satellite data updated';
      } else if (gotChlorophyll) {
        status = 'Live chlorophyll data updated';
      } else if (gotSST) {
        status = 'Live SST data updated';
      } else {
        status = 'Marine data partially available';
      }

      setState(() {
        satelliteLoading = false;
        satelliteStatus = status;

        if (!gotPFZ) {
          pfzStatus = 'PFZ data unavailable';
        }
      });
    } else {
      setState(() {
        satelliteLoading = false;
        satelliteStatus = 'Marine satellite data unavailable';
        pfzStatus = 'Fishing potential unavailable';
      });
    }
  }

  // ============================================================
  // CHLOROPHYLL API
  // ============================================================

  Future<Map<String, dynamic>> _requestChlorophyll(
    double latitude,
    double longitude,
  ) async {
    final uri = Uri.parse(
      '$apiBaseUrl/satellite/chlorophyll'
      '?latitude=$latitude'
      '&longitude=$longitude'
      '&radius=1.5',
    );

    final response = await http.get(uri).timeout(const Duration(seconds: 20));

    if (response.statusCode != 200) {
      throw Exception('Chlorophyll API ${response.statusCode}');
    }

    final decoded = jsonDecode(response.body);

    return Map<String, dynamic>.from(decoded);
  }

  // ============================================================
  // SST API
  // ============================================================

  Future<Map<String, dynamic>> _requestSST(
    double latitude,
    double longitude,
  ) async {
    final uri = Uri.parse(
      '$apiBaseUrl/satellite/sst'
      '?latitude=$latitude'
      '&longitude=$longitude'
      '&radius=1.5',
    );

    final response = await http.get(uri).timeout(const Duration(seconds: 20));

    if (response.statusCode != 200) {
      throw Exception('SST API ${response.statusCode}');
    }

    final decoded = jsonDecode(response.body);

    return Map<String, dynamic>.from(decoded);
  }

  // ============================================================
  // PFZ API
  // ============================================================

  Future<Map<String, dynamic>> _requestPFZ(
    double latitude,
    double longitude,
  ) async {
    final uri = Uri.parse(
      '$apiBaseUrl/pfz/potential'
      '?latitude=$latitude'
      '&longitude=$longitude'
      '&radius=1.5',
    );

    final response = await http.get(uri).timeout(const Duration(seconds: 30));

    if (response.statusCode != 200) {
      throw Exception('PFZ API ${response.statusCode}');
    }

    final decoded = jsonDecode(response.body);

    return Map<String, dynamic>.from(decoded);
  }

  // ============================================================
  // APPLY CHLOROPHYLL
  // ============================================================

  void _applyChlorophyllData(Map<String, dynamic> data) {
    final rawPoints = data['points'];
    final rawHotspots = data['hotspots'];

    final points = rawPoints is List
        ? rawPoints
              .whereType<Map>()
              .map((item) => Map<String, dynamic>.from(item))
              .toList()
        : <Map<String, dynamic>>[];

    final hotspots = rawHotspots is List
        ? rawHotspots
              .whereType<Map>()
              .map((item) => Map<String, dynamic>.from(item))
              .toList()
        : <Map<String, dynamic>>[];

    final rawRange = data['range'];

    final range = rawRange is Map
        ? Map<String, dynamic>.from(rawRange)
        : <String, dynamic>{};

    final minimum = (range['minimum'] as num?)?.toDouble();

    final maximum = (range['maximum'] as num?)?.toDouble();

    final threshold = (data['hotspot_threshold'] as num?)?.toDouble();

    if (!mounted) return;

    setState(() {
      chlorophyllPoints = points;
      hotspotData = hotspots;

      minChlorophyll = minimum;
      maxChlorophyll = maximum;

      chlorophyllThreshold = threshold;
    });
  }

  // ============================================================
  // APPLY SST
  // ============================================================

  void _applySSTData(Map<String, dynamic> data) {
    final rawPoints = data['points'];

    final points = rawPoints is List
        ? rawPoints
              .whereType<Map>()
              .map((item) => Map<String, dynamic>.from(item))
              .toList()
        : <Map<String, dynamic>>[];

    final rawRange = data['range'];

    final range = rawRange is Map
        ? Map<String, dynamic>.from(rawRange)
        : <String, dynamic>{};

    final minimum = (range['minimum'] as num?)?.toDouble();

    final maximum = (range['maximum'] as num?)?.toDouble();

    if (!mounted) return;

    setState(() {
      sstPoints = points;

      minSST = minimum;
      maxSST = maximum;

      sstStatus = data['status'] == 'ok'
          ? 'SST updated'
          : data['message'] ?? 'No SST data';
    });
  }

  // ============================================================
  // APPLY PFZ
  // ============================================================

  void _applyPFZData(Map<String, dynamic> data) {
    /*
     * Backend response:
     *
     * {
     *   "status": "ok",
     *   "total_zones": 3,
     *   "high": 1,
     *   "moderate": 2,
     *   "low": 0,
     *   "points": [...]
     * }
     *
     * IMPORTANT:
     * Backend does NOT use "zones".
     * It uses "points".
     */

    final rawPoints = data['points'];

    final points = rawPoints is List
        ? rawPoints
              .whereType<Map>()
              .map((item) => Map<String, dynamic>.from(item))
              .toList()
        : <Map<String, dynamic>>[];

    /*
     * Your actual backend response puts:
     *
     * total_zones
     * high
     * moderate
     * low
     *
     * directly at root level.
     *
     * So we read them directly.
     *
     * We also keep support for "summary"
     * in case backend changes later.
     */

    final rawSummary = data['summary'];

    final summary = rawSummary is Map
        ? Map<String, dynamic>.from(rawSummary)
        : <String, dynamic>{};

    final total =
        (data['total_zones'] as num?)?.toInt() ??
        (summary['total_zones'] as num?)?.toInt() ??
        points.length;

    final high =
        (data['high'] as num?)?.toInt() ??
        (summary['high'] as num?)?.toInt() ??
        points
            .where(
              (point) => point['potential']?.toString().toUpperCase() == 'HIGH',
            )
            .length;

    final moderate =
        (data['moderate'] as num?)?.toInt() ??
        (summary['moderate'] as num?)?.toInt() ??
        points
            .where(
              (point) =>
                  point['potential']?.toString().toUpperCase() == 'MODERATE',
            )
            .length;

    final low =
        (data['low'] as num?)?.toInt() ??
        (summary['low'] as num?)?.toInt() ??
        points
            .where(
              (point) => point['potential']?.toString().toUpperCase() == 'LOW',
            )
            .length;

    if (!mounted) return;

    setState(() {
      pfzPoints = points;

      pfzTotal = total;

      pfzHigh = high;
      pfzModerate = moderate;
      pfzLow = low;

      pfzStatus = data['status'] == 'ok'
          ? '$high high • $moderate moderate • $low low'
          : data['message'] ?? 'No fishing potential data';
    });
  }

  // ============================================================
  // CHLOROPHYLL MAP LAYER
  // ============================================================

  List<CircleMarker> get chlorophyllLayer {
    if (!showChlorophyll || chlorophyllPoints.isEmpty) {
      return [];
    }

    final minimum = minChlorophyll ?? 0;
    final maximum = maxChlorophyll ?? 1;

    final difference = math.max(maximum - minimum, 0.0001);

    return chlorophyllPoints.map((point) {
      final lat = (point['latitude'] as num).toDouble();

      final lon = (point['longitude'] as num).toDouble();

      final value = (point['chlorophyll'] as num).toDouble();

      var normalized = (value - minimum) / difference;

      normalized = normalized.clamp(0.0, 1.0);

      final color = _chlorophyllColor(normalized);

      return CircleMarker(
        point: LatLng(lat, lon),
        radius: 2600,
        useRadiusInMeter: true,
        color: color.withValues(alpha: .38),
        borderColor: color.withValues(alpha: .55),
        borderStrokeWidth: .7,
      );
    }).toList();
  }

  // ============================================================
  // CHLOROPHYLL COLOR
  // ============================================================

  Color _chlorophyllColor(double value) {
    if (value < .25) {
      return const Color(0xFFB8D8D0);
    }

    if (value < .50) {
      return const Color(0xFF69B39F);
    }

    if (value < .75) {
      return const Color(0xFFE1B85A);
    }

    return const Color(0xFFD36E55);
  }

  // ============================================================
  // SST MAP LAYER
  // ============================================================

  List<CircleMarker> get sstLayer {
    if (!showSST || sstPoints.isEmpty) {
      return [];
    }

    final minimum = minSST ?? 20;
    final maximum = maxSST ?? 35;

    final difference = math.max(maximum - minimum, .0001);

    return sstPoints.map((point) {
      final lat = (point['latitude'] as num).toDouble();

      final lon = (point['longitude'] as num).toDouble();

      final temperature = (point['sst'] as num).toDouble();

      var normalized = (temperature - minimum) / difference;

      normalized = normalized.clamp(0.0, 1.0);

      final color = _sstColor(normalized);

      return CircleMarker(
        point: LatLng(lat, lon),
        radius: 2300,
        useRadiusInMeter: true,
        color: color.withValues(alpha: .24),
        borderColor: color.withValues(alpha: .40),
        borderStrokeWidth: .5,
      );
    }).toList();
  }

  // ============================================================
  // SST COLOR
  // ============================================================

  Color _sstColor(double value) {
    if (value < .20) {
      return const Color(0xFF3B82C4);
    }

    if (value < .40) {
      return const Color(0xFF4FB6C2);
    }

    if (value < .60) {
      return const Color(0xFFE0C35A);
    }

    if (value < .80) {
      return const Color(0xFFE58B4A);
    }

    return const Color(0xFFD6534F);
  }

  // ============================================================
  // SST CLICKABLE MARKERS
  // ============================================================

  List<Marker> get sstMarkers {
    if (!showSST || sstPoints.isEmpty) {
      return [];
    }

    final sampled = <Map<String, dynamic>>[];

    for (int i = 0; i < sstPoints.length; i += 20) {
      sampled.add(sstPoints[i]);
    }

    return sampled.map((point) {
      final lat = (point['latitude'] as num).toDouble();

      final lon = (point['longitude'] as num).toDouble();

      final temperature = (point['sst'] as num).toDouble();

      return Marker(
        point: LatLng(lat, lon),
        width: 42,
        height: 42,
        child: GestureDetector(
          onTap: () {
            _showSSTInfo(LatLng(lat, lon), temperature);
          },
          child: Container(
            alignment: Alignment.center,
            decoration: BoxDecoration(
              shape: BoxShape.circle,
              color: Colors.white.withValues(alpha: .88),
              border: Border.all(color: const Color(0xFFD65C4A), width: 1.4),
            ),
            child: const Icon(
              Icons.thermostat_outlined,
              size: 18,
              color: Color(0xFFD65C4A),
            ),
          ),
        ),
      );
    }).toList();
  }

  // ============================================================
  // PFZ MARKERS
  // ============================================================

  List<Marker> get pfzMarkers {
    if (!showPFZ || pfzPoints.isEmpty) {
      return [];
    }

    return pfzPoints.map((point) {
      final lat = (point['latitude'] as num).toDouble();

      final lon = (point['longitude'] as num).toDouble();

      final score =
          (point['fishing_score'] as num?)?.toDouble() ??
          (point['score'] as num?)?.toDouble() ??
          0;

      final level = _getPFZLevel(point);

      return Marker(
        point: LatLng(lat, lon),
        width: 72,
        height: 72,
        child: GestureDetector(
          onTap: () {
            _showPFZInfo(point);
          },
          child: _PFZMarker(level: level, score: score),
        ),
      );
    }).toList();
  }

  // ============================================================
  // PFZ LEVEL
  // ============================================================

  String _getPFZLevel(Map<String, dynamic> point) {
    final potential = point['potential'];

    if (potential != null) {
      return potential.toString().toUpperCase();
    }

    final score =
        (point['fishing_score'] as num?)?.toDouble() ??
        (point['score'] as num?)?.toDouble() ??
        0;

    if (score >= 70) {
      return 'HIGH';
    }

    if (score >= 40) {
      return 'MODERATE';
    }

    return 'LOW';
  }

  // ============================================================
  // PFZ COLOR
  // ============================================================

  Color _pfzColor(String level) {
    switch (level.toUpperCase()) {
      case 'HIGH':
        return const Color(0xFF3F8A70);

      case 'MODERATE':
        return const Color(0xFFD49A45);

      default:
        return const Color(0xFF7C9AA0);
    }
  }

  // ============================================================
  // PFZ INFO
  // ============================================================

  void _showPFZInfo(Map<String, dynamic> point) {
    final score =
        (point['fishing_score'] as num?)?.toDouble() ??
        (point['score'] as num?)?.toDouble() ??
        0;

    final level = _getPFZLevel(point);

    final chlorophyll = (point['chlorophyll'] as num?)?.toDouble();

    final sst = (point['sst'] as num?)?.toDouble();

    final distance = (point['distance_km'] as num?)?.toDouble();

    final lat = (point['latitude'] as num?)?.toDouble();

    final lon = (point['longitude'] as num?)?.toDouble();

    selectedPFZScore = score;
    selectedPFZLevel = level;

    showModalBottomSheet(
      context: context,
      backgroundColor: const Color(0xFFF4F7F2),
      shape: const RoundedRectangleBorder(
        borderRadius: BorderRadius.vertical(top: Radius.circular(28)),
      ),
      builder: (context) {
        final color = _pfzColor(level);

        return Padding(
          padding: const EdgeInsets.fromLTRB(22, 22, 22, 28),
          child: Column(
            mainAxisSize: MainAxisSize.min,
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              Row(
                children: [
                  Container(
                    width: 48,
                    height: 48,
                    decoration: BoxDecoration(
                      color: color.withValues(alpha: .14),
                      borderRadius: BorderRadius.circular(15),
                    ),
                    child: Icon(
                      Icons.phishing_outlined,
                      color: color,
                      size: 25,
                    ),
                  ),
                  const SizedBox(width: 12),
                  const Expanded(
                    child: Text(
                      'Fishing Potential Zone',
                      style: TextStyle(
                        fontSize: 19,
                        fontWeight: FontWeight.w700,
                        color: Color(0xFF183B3D),
                      ),
                    ),
                  ),
                ],
              ),

              const SizedBox(height: 18),

              Container(
                padding: const EdgeInsets.symmetric(
                  horizontal: 13,
                  vertical: 10,
                ),
                decoration: BoxDecoration(
                  color: color.withValues(alpha: .12),
                  borderRadius: BorderRadius.circular(14),
                ),
                child: Row(
                  children: [
                    Icon(Icons.analytics_outlined, size: 20, color: color),
                    const SizedBox(width: 8),
                    Text(
                      level,
                      style: TextStyle(
                        fontWeight: FontWeight.w800,
                        fontSize: 15,
                        color: color,
                      ),
                    ),
                    const Spacer(),
                    Text(
                      '${score.toStringAsFixed(1)} / 100',
                      style: const TextStyle(
                        fontWeight: FontWeight.w800,
                        fontSize: 15,
                        color: Color(0xFF234E50),
                      ),
                    ),
                  ],
                ),
              ),

              const SizedBox(height: 15),

              Row(
                children: [
                  _infoChip(
                    'CHLOROPHYLL',
                    chlorophyll == null
                        ? '—'
                        : '${chlorophyll.toStringAsFixed(2)} mg/m³',
                  ),
                  const SizedBox(width: 7),
                  _infoChip(
                    'SST',
                    sst == null ? '—' : '${sst.toStringAsFixed(2)} °C',
                  ),
                ],
              ),

              const SizedBox(height: 12),

              if (distance != null)
                Text(
                  'Distance from analysis point: '
                  '${distance.toStringAsFixed(1)} km',
                  style: const TextStyle(
                    fontSize: 11,
                    color: Color(0xFF71817C),
                  ),
                ),

              if (lat != null && lon != null)
                Padding(
                  padding: const EdgeInsets.only(top: 7),
                  child: Text(
                    '${lat.toStringAsFixed(4)}° N  '
                    '${lon.toStringAsFixed(4)}° E',
                    style: const TextStyle(
                      fontSize: 11,
                      color: Color(0xFF71817C),
                    ),
                  ),
                ),

              const SizedBox(height: 12),

              const Text(
                'PFZ baseline combines satellite '
                'chlorophyll and sea-surface temperature. '
                'It indicates potential fishing conditions '
                'and does not confirm fish presence.',
                style: TextStyle(
                  fontSize: 11,
                  height: 1.45,
                  color: Color(0xFF71817C),
                ),
              ),
            ],
          ),
        );
      },
    );
  }

  // ============================================================
  // SST INFO
  // ============================================================

  void _showSSTInfo(LatLng point, double temperature) {
    showModalBottomSheet(
      context: context,
      backgroundColor: const Color(0xFFF4F7F2),
      shape: const RoundedRectangleBorder(
        borderRadius: BorderRadius.vertical(top: Radius.circular(28)),
      ),
      builder: (context) {
        return Padding(
          padding: const EdgeInsets.fromLTRB(24, 22, 24, 28),
          child: Column(
            mainAxisSize: MainAxisSize.min,
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              const Text(
                'Sea Surface Temperature',
                style: TextStyle(
                  fontSize: 19,
                  fontWeight: FontWeight.w700,
                  color: Color(0xFF183B3D),
                ),
              ),

              const SizedBox(height: 18),

              Row(
                children: [
                  _infoChip('SST', '${temperature.toStringAsFixed(2)} °C'),
                  const SizedBox(width: 8),
                  _infoChip('SOURCE', 'NOAA ACSPO'),
                ],
              ),

              const SizedBox(height: 15),

              Text(
                '${point.latitude.toStringAsFixed(4)}° N  '
                '${point.longitude.toStringAsFixed(4)}° E',
                style: const TextStyle(fontSize: 11, color: Color(0xFF71817C)),
              ),
            ],
          ),
        );
      },
    );
  }

  bool showGeofences = true;

  double geofenceDistanceKm = 1.4;
  double geofenceEtaMinutes = 8;

  double geofenceHeading = 0.0;
  // ============================================================
  // GEO-FENCE INTELLIGENCE
  // ============================================================

  List<Polygon> get geofencePolygons {
    final p = geofenceAnchor ?? currentLocation;

    // Demo geofence geometry.
    // Replace these coordinates later with official GIS boundaries.
    final restrictedZone = <LatLng>[
      LatLng(p.latitude + 0.010, p.longitude + 0.006),
      LatLng(p.latitude + 0.016, p.longitude + 0.022),
      LatLng(p.latitude + 0.004, p.longitude + 0.034),
      LatLng(p.latitude - 0.010, p.longitude + 0.025),
      LatLng(p.latitude - 0.012, p.longitude + 0.006),
    ];

    final protectedArea = <LatLng>[
      LatLng(p.latitude + 0.055, p.longitude - 0.045),
      LatLng(p.latitude + 0.072, p.longitude - 0.015),
      LatLng(p.latitude + 0.050, p.longitude + 0.010),
      LatLng(p.latitude + 0.025, p.longitude - 0.005),
      LatLng(p.latitude + 0.030, p.longitude - 0.040),
    ];

    final sensitiveZone = <LatLng>[
      LatLng(p.latitude - 0.055, p.longitude + 0.055),
      LatLng(p.latitude - 0.038, p.longitude + 0.085),
      LatLng(p.latitude - 0.065, p.longitude + 0.105),
      LatLng(p.latitude - 0.090, p.longitude + 0.075),
      LatLng(p.latitude - 0.082, p.longitude + 0.045),
    ];

    final maritimeBoundary = <LatLng>[
      LatLng(p.latitude - 0.12, p.longitude - 0.10),
      LatLng(p.latitude - 0.02, p.longitude - 0.04),
      LatLng(p.latitude + 0.08, p.longitude - 0.015),
      LatLng(p.latitude + 0.16, p.longitude + 0.015),
    ];

    return [
      Polygon(
        points: restrictedZone,
        color: const Color(0xFFFF9B62).withValues(alpha: .22),
        borderColor: const Color(0xFFFF8A3D),
        borderStrokeWidth: 2.5,
        label: 'Restricted Fishing Zone',
        labelStyle: const TextStyle(
          fontSize: 11,
          fontWeight: FontWeight.w700,
          color: Color(0xFF9A4C18),
        ),
      ),

      Polygon(
        points: protectedArea,
        color: const Color(0xFF9C6ADE).withValues(alpha: .20),
        borderColor: const Color(0xFF8752C7),
        borderStrokeWidth: 2.5,
        label: 'Marine Protected Area',
        labelStyle: const TextStyle(
          fontSize: 11,
          fontWeight: FontWeight.w700,
          color: Color(0xFF63399A),
        ),
      ),

      Polygon(
        points: sensitiveZone,
        color: const Color(0xFFE9C84A).withValues(alpha: .22),
        borderColor: const Color(0xFFD0AA18),
        borderStrokeWidth: 2.5,
        label: 'Ecologically Sensitive Zone',
        labelStyle: const TextStyle(
          fontSize: 11,
          fontWeight: FontWeight.w700,
          color: Color(0xFF806A08),
        ),
      ),
    ];
  }

  List<Polyline> get maritimeBoundaryLayer {
    final p = geofenceAnchor ?? currentLocation;

    return [
      Polyline(
        points: [
          LatLng(p.latitude - 0.12, p.longitude - 0.10),
          LatLng(p.latitude - 0.02, p.longitude - 0.04),
          LatLng(p.latitude + 0.08, p.longitude - 0.015),
          LatLng(p.latitude + 0.16, p.longitude + 0.015),
        ],
        color: const Color(0xFFD84A45),
        strokeWidth: 3,
      ),
    ];
  }

  // ============================================================
  // RISK ZONES
  // ============================================================

  List<CircleMarker> get riskZones {
    final p = currentLocation;

    return [
      CircleMarker(
        point: LatLng(p.latitude + .04, p.longitude + .03),
        radius: 8500,
        useRadiusInMeter: true,
        color: const Color(0xFFC96D63).withValues(alpha: .17),
        borderColor: const Color(0xFFC96D63).withValues(alpha: .55),
        borderStrokeWidth: 1.5,
      ),
      CircleMarker(
        point: LatLng(p.latitude - .09, p.longitude - .04),
        radius: 5500,
        useRadiusInMeter: true,
        color: const Color(0xFFE1A45B).withValues(alpha: .15),
        borderColor: const Color(0xFFE1A45B).withValues(alpha: .5),
        borderStrokeWidth: 1.5,
      ),
    ];
  }

  // ============================================================
  // SAFE ZONES
  // ============================================================

  List<CircleMarker> get safeZones {
    final p = currentLocation;

    return [
      CircleMarker(
        point: LatLng(p.latitude + .02, p.longitude - .10),
        radius: 6500,
        useRadiusInMeter: true,
        color: const Color(0xFF76A997).withValues(alpha: .13),
        borderColor: const Color(0xFF76A997).withValues(alpha: .5),
        borderStrokeWidth: 1.5,
      ),
    ];
  }

  // ============================================================
  // INFO CHIP
  // ============================================================

  Widget _infoChip(String title, String value) {
    return Expanded(
      child: Container(
        padding: const EdgeInsets.symmetric(horizontal: 10, vertical: 10),
        decoration: BoxDecoration(
          color: Colors.white,
          borderRadius: BorderRadius.circular(14),
        ),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Text(
              title,
              style: const TextStyle(
                fontSize: 8,
                letterSpacing: 1,
                fontWeight: FontWeight.w700,
                color: Color(0xFF82928D),
              ),
            ),
            const SizedBox(height: 4),
            Text(
              value,
              maxLines: 1,
              overflow: TextOverflow.ellipsis,
              style: const TextStyle(
                fontSize: 11,
                fontWeight: FontWeight.w700,
                color: Color(0xFF244F50),
              ),
            ),
          ],
        ),
      ),
    );
  }

  // ============================================================
  // BUILD
  // ============================================================

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      backgroundColor: const Color(0xFFF2F6F1),
      body: Stack(
        children: [
          FlutterMap(
            mapController: _mapController,
            options: MapOptions(
              initialCenter: currentLocation,
              initialZoom: 7,
              minZoom: 3,
              maxZoom: 14,
            ),
            children: [
              TileLayer(
                urlTemplate:
                    'https://tile.openstreetmap.org/'
                    '{z}/{x}/{y}.png',
                userAgentPackageName: 'com.marineintelligence.app',
              ),

              if (showChlorophyll) CircleLayer(circles: chlorophyllLayer),

              if (showSST) CircleLayer(circles: sstLayer),

              // ==================================================
              // GEO-FENCE INTELLIGENCE
              // ==================================================
              if (showGeofences) PolygonLayer(polygons: geofencePolygons),

              if (showGeofences)
                PolylineLayer(polylines: maritimeBoundaryLayer),

              if (showRisk) CircleLayer(circles: riskZones),

              if (showSafeZones) CircleLayer(circles: safeZones),

              if (showPFZ) MarkerLayer(markers: pfzMarkers),

              if (showSST) MarkerLayer(markers: sstMarkers),

              MarkerLayer(
                markers: [
                  Marker(
                    point: currentLocation,
                    width: 58,
                    height: 58,
                    child: const _UserLocationMarker(),
                  ),
                ],
              ),
            ],
          ),

          // ======================================================
          // TOP BAR
          // ======================================================
          Positioned(
            top: 0,
            left: 0,
            right: 0,
            child: SafeArea(
              child: Padding(
                padding: const EdgeInsets.fromLTRB(18, 12, 18, 0),
                child: Row(
                  children: [
                    _roundButton(Icons.arrow_back_ios_new_rounded, () {
                      Navigator.pop(context);
                    }),

                    const SizedBox(width: 12),

                    Expanded(
                      child: Container(
                        padding: const EdgeInsets.symmetric(
                          horizontal: 17,
                          vertical: 13,
                        ),
                        decoration: BoxDecoration(
                          color: Colors.white.withValues(alpha: .94),
                          borderRadius: BorderRadius.circular(19),
                          boxShadow: [
                            BoxShadow(
                              color: Colors.black.withValues(alpha: .08),
                              blurRadius: 18,
                              offset: const Offset(0, 7),
                            ),
                          ],
                        ),
                        child: const Row(
                          children: [
                            Icon(
                              Icons.explore_outlined,
                              size: 19,
                              color: Color(0xFF326E65),
                            ),
                            SizedBox(width: 9),
                            Text(
                              'Marine Intelligence',
                              style: TextStyle(
                                fontSize: 15,
                                fontWeight: FontWeight.w700,
                                color: Color(0xFF183B3D),
                              ),
                            ),
                          ],
                        ),
                      ),
                    ),
                  ],
                ),
              ),
            ),
          ),

          // ======================================================
          // STATUS
          // ======================================================
          Positioned(top: 106, left: 17, child: _satelliteStatus()),

          // ======================================================
          // LAYERS
          // ======================================================
          Positioned(top: 105, right: 17, child: _layerControl()),

          // ======================================================
          // MAP CONTROLS
          // ======================================================
          Positioned(
            right: 17,
            bottom: 205,
            child: Column(
              children: [
                _mapButton(Icons.add, () {
                  final zoom = _mapController.camera.zoom;

                  _mapController.move(
                    _mapController.camera.center,
                    math.min(14, zoom + 1),
                  );
                }),

                const SizedBox(height: 7),

                _mapButton(Icons.remove, () {
                  final zoom = _mapController.camera.zoom;

                  _mapController.move(
                    _mapController.camera.center,
                    math.max(3, zoom - 1),
                  );
                }),

                const SizedBox(height: 7),

                _mapButton(Icons.my_location_rounded, () {
                  _mapController.move(currentLocation, 9);
                }),

                const SizedBox(height: 7),

                _mapButton(
                  satelliteLoading ? Icons.hourglass_top : Icons.refresh,
                  () {
                    if (!satelliteLoading) {
                      _loadAllMarineData();
                    }
                  },
                ),
              ],
            ),
          ),

          // ======================================================
          // BOTTOM PANEL
          // ======================================================
          Positioned(
            left: 16,
            right: 16,
            bottom: 18,
            child: Column(
              mainAxisSize: MainAxisSize.min,
              children: [if (showGeofences) _geofenceWarning(), _bottomPanel()],
            ),
          ),
        ],
      ),
    );
  }

  // ============================================================
  // STATUS WIDGET
  // ============================================================

  Widget _satelliteStatus() {
    return Container(
      constraints: const BoxConstraints(maxWidth: 240),
      padding: const EdgeInsets.symmetric(horizontal: 12, vertical: 9),
      decoration: BoxDecoration(
        color: Colors.white.withValues(alpha: .94),
        borderRadius: BorderRadius.circular(16),
        boxShadow: [
          BoxShadow(
            color: Colors.black.withValues(alpha: .08),
            blurRadius: 16,
            offset: const Offset(0, 6),
          ),
        ],
      ),
      child: Row(
        mainAxisSize: MainAxisSize.min,
        children: [
          if (satelliteLoading)
            const SizedBox(
              width: 13,
              height: 13,
              child: CircularProgressIndicator(strokeWidth: 1.8),
            )
          else
            Container(
              width: 8,
              height: 8,
              decoration: const BoxDecoration(
                shape: BoxShape.circle,
                color: Color(0xFF5B9B83),
              ),
            ),

          const SizedBox(width: 7),

          Flexible(
            child: Text(
              satelliteStatus,
              style: const TextStyle(
                fontSize: 10,
                fontWeight: FontWeight.w600,
                color: Color(0xFF315052),
              ),
              maxLines: 2,
              overflow: TextOverflow.ellipsis,
            ),
          ),
        ],
      ),
    );
  }

  // ============================================================
  // LAYER CONTROL
  // ============================================================

  Widget _layerControl() {
    return Container(
      width: 210,
      padding: const EdgeInsets.all(10),
      decoration: BoxDecoration(
        color: Colors.white.withValues(alpha: .96),
        borderRadius: BorderRadius.circular(20),
        boxShadow: [
          BoxShadow(
            color: Colors.black.withValues(alpha: .10),
            blurRadius: 22,
            offset: const Offset(0, 8),
          ),
        ],
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          const Padding(
            padding: EdgeInsets.fromLTRB(7, 4, 7, 8),
            child: Text(
              'MAP LAYERS',
              style: TextStyle(
                fontSize: 9,
                letterSpacing: 1.6,
                fontWeight: FontWeight.w800,
                color: Color(0xFF80928C),
              ),
            ),
          ),

          _layerSwitch('Fishing Potential', Icons.phishing_outlined, showPFZ, (
            value,
          ) {
            setState(() {
              showPFZ = value;
            });
          }),

          _layerSwitch('Chlorophyll', Icons.grass_outlined, showChlorophyll, (
            value,
          ) {
            setState(() {
              showChlorophyll = value;
            });
          }),

          _layerSwitch('SST', Icons.thermostat_outlined, showSST, (value) {
            setState(() {
              showSST = value;
            });
          }),
          _layerSwitch(
            'Geofence intelligence',
            Icons.gps_fixed_rounded,
            showGeofences,
            (value) {
              setState(() {
                showGeofences = value;
              });
            },
          ),
          _layerSwitch('Risk zones', Icons.warning_amber_rounded, showRisk, (
            value,
          ) {
            setState(() {
              showRisk = value;
            });
          }),

          _layerSwitch('Safe zones', Icons.shield_outlined, showSafeZones, (
            value,
          ) {
            setState(() {
              showSafeZones = value;
            });
          }),
        ],
      ),
    );
  }

  // ============================================================
  // LAYER SWITCH
  // ============================================================

  Widget _layerSwitch(
    String title,
    IconData icon,
    bool value,
    ValueChanged<bool> onChanged,
  ) {
    return InkWell(
      borderRadius: BorderRadius.circular(13),
      onTap: () {
        onChanged(!value);
      },
      child: Padding(
        padding: const EdgeInsets.symmetric(horizontal: 6, vertical: 5),
        child: Row(
          children: [
            Icon(
              icon,
              size: 17,
              color: value ? const Color(0xFF326E65) : const Color(0xFF9AA8A4),
            ),

            const SizedBox(width: 9),

            Expanded(
              child: Text(
                title,
                style: TextStyle(
                  fontSize: 12,
                  fontWeight: value ? FontWeight.w700 : FontWeight.w500,
                  color: const Color(0xFF315052),
                ),
              ),
            ),

            SizedBox(
              width: 30,
              height: 18,
              child: Switch(
                value: value,
                onChanged: onChanged,
                materialTapTargetSize: MaterialTapTargetSize.shrinkWrap,
              ),
            ),
          ],
        ),
      ),
    );
  }

  // ============================================================
  // BOTTOM PANEL
  // ============================================================
  Widget _geofenceWarning() {
    return Align(
      alignment: Alignment.centerLeft,
      child: Container(
        width: 300,
        margin: const EdgeInsets.only(bottom: 10),
        padding: const EdgeInsets.symmetric(horizontal: 12, vertical: 10),
        decoration: BoxDecoration(
          color: const Color(0xFFFFF4E8),
          borderRadius: BorderRadius.circular(16),
          border: Border.all(color: const Color(0xFFF0B36B), width: 1),
          boxShadow: [
            BoxShadow(
              color: Colors.black.withValues(alpha: .08),
              blurRadius: 12,
              offset: const Offset(0, 4),
            ),
          ],
        ),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Row(
              children: [
                Container(
                  width: 30,
                  height: 30,
                  decoration: const BoxDecoration(
                    color: Color(0xFFFFE0BD),
                    shape: BoxShape.circle,
                  ),
                  child: const Icon(
                    Icons.warning_amber_rounded,
                    color: Color(0xFFC56A20),
                    size: 17,
                  ),
                ),
                const SizedBox(width: 8),

                const Expanded(
                  child: Text(
                    'GEOFENCE WARNING',
                    style: TextStyle(
                      fontSize: 9,
                      letterSpacing: 1.1,
                      fontWeight: FontWeight.w800,
                      color: Color(0xFF9A531D),
                    ),
                  ),
                ),

                Text(
                  '${geofenceDistanceKm.toStringAsFixed(1)} km',
                  style: const TextStyle(
                    fontSize: 13,
                    fontWeight: FontWeight.w800,
                    color: Color(0xFF9A531D),
                  ),
                ),
              ],
            ),

            const SizedBox(height: 7),

            const Text(
              'RESTRICTED FISHING ZONE',
              style: TextStyle(
                fontSize: 10,
                fontWeight: FontWeight.w800,
                letterSpacing: .5,
                color: Color(0xFF7B481F),
              ),
            ),

            const SizedBox(height: 3),

            Text(
              'You may enter this zone in '
              '${geofenceEtaMinutes.toStringAsFixed(0)} minutes '
              'if you continue on your current heading.',
              style: const TextStyle(
                fontSize: 10,
                height: 1.3,
                color: Color(0xFF6F5848),
              ),
            ),

            const SizedBox(height: 6),

            Row(
              children: [
                const Icon(
                  Icons.navigation_rounded,
                  size: 13,
                  color: Color(0xFFC56A20),
                ),
                const SizedBox(width: 5),
                Text(
                  'Heading ${geofenceHeading.toStringAsFixed(0)}°',
                  style: const TextStyle(
                    fontSize: 9,
                    fontWeight: FontWeight.w700,
                    color: Color(0xFF9A531D),
                  ),
                ),
              ],
            ),
          ],
        ),
      ),
    );
  }

  Widget _bottomPanel() {
    return Container(
      padding: const EdgeInsets.fromLTRB(17, 15, 17, 16),
      decoration: BoxDecoration(
        color: const Color(0xFF183F41).withValues(alpha: .96),
        borderRadius: BorderRadius.circular(25),
        boxShadow: [
          BoxShadow(
            color: Colors.black.withValues(alpha: .18),
            blurRadius: 25,
            offset: const Offset(0, 10),
          ),
        ],
      ),
      child: Column(
        children: [
          Row(
            children: [
              Container(
                width: 9,
                height: 9,
                decoration: const BoxDecoration(
                  shape: BoxShape.circle,
                  color: Color(0xFF83C4A9),
                ),
              ),

              const SizedBox(width: 8),

              const Text(
                'LIVE MARINE VIEW',
                style: TextStyle(
                  fontSize: 9,
                  letterSpacing: 1.7,
                  fontWeight: FontWeight.w800,
                  color: Color(0xFFAED4C8),
                ),
              ),

              const Spacer(),

              const Text(
                'VIIRS + ACSPO',
                style: TextStyle(
                  fontSize: 8,
                  letterSpacing: 1.2,
                  color: Color(0xFF8BAAA4),
                ),
              ),
            ],
          ),

          const SizedBox(height: 13),

          Row(
            children: [
              _bottomMetric(
                Icons.phishing_outlined,
                'PFZ',
                pfzTotal == 0 ? 'None' : '$pfzTotal zones',
              ),

              _bottomMetric(Icons.trending_up_rounded, 'HIGH', '$pfzHigh'),

              _bottomMetric(
                Icons.grass_outlined,
                'CHL-a',
                maxChlorophyll == null
                    ? 'No data'
                    : maxChlorophyll!.toStringAsFixed(2),
              ),

              _bottomMetric(
                Icons.thermostat_outlined,
                'SST',
                maxSST == null ? 'No data' : '${maxSST!.toStringAsFixed(1)}°C',
              ),
            ],
          ),

          const SizedBox(height: 12),

          Row(
            children: [
              const Icon(
                Icons.location_on_outlined,
                size: 14,
                color: Color(0xFF9FC7BE),
              ),

              const SizedBox(width: 5),

              Expanded(
                child: Text(
                  '${currentLocation.latitude.toStringAsFixed(4)}° N  '
                  '${currentLocation.longitude.toStringAsFixed(4)}° E',
                  style: const TextStyle(
                    fontSize: 10,
                    color: Color(0xFF9DB9B3),
                  ),
                ),
              ),

              Flexible(
                child: Text(
                  satelliteLoading ? 'Updating...' : pfzStatus,
                  textAlign: TextAlign.end,
                  maxLines: 2,
                  overflow: TextOverflow.ellipsis,
                  style: const TextStyle(fontSize: 9, color: Color(0xFF789A93)),
                ),
              ),
            ],
          ),
        ],
      ),
    );
  }

  // ============================================================
  // BOTTOM METRIC
  // ============================================================

  Widget _bottomMetric(IconData icon, String title, String value) {
    return Expanded(
      child: Row(
        children: [
          Icon(icon, size: 16, color: const Color(0xFF8DC7B5)),

          const SizedBox(width: 7),

          Expanded(
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Text(
                  title,
                  style: const TextStyle(
                    fontSize: 8,
                    letterSpacing: 1.1,
                    color: Color(0xFF779B94),
                    fontWeight: FontWeight.w700,
                  ),
                ),

                const SizedBox(height: 2),

                Text(
                  value,
                  maxLines: 1,
                  overflow: TextOverflow.ellipsis,
                  style: const TextStyle(
                    fontSize: 10,
                    color: Colors.white,
                    fontWeight: FontWeight.w600,
                  ),
                ),
              ],
            ),
          ),
        ],
      ),
    );
  }

  // ============================================================
  // ROUND BUTTON
  // ============================================================

  Widget _roundButton(IconData icon, VoidCallback onTap) {
    return Material(
      color: Colors.white.withValues(alpha: .94),
      borderRadius: BorderRadius.circular(17),
      elevation: 3,
      child: InkWell(
        borderRadius: BorderRadius.circular(17),
        onTap: onTap,
        child: SizedBox(
          width: 48,
          height: 48,
          child: Icon(icon, size: 18, color: const Color(0xFF234E50)),
        ),
      ),
    );
  }

  // ============================================================
  // MAP BUTTON
  // ============================================================

  Widget _mapButton(IconData icon, VoidCallback onTap) {
    return Material(
      color: Colors.white.withValues(alpha: .94),
      borderRadius: BorderRadius.circular(15),
      elevation: 3,
      child: InkWell(
        borderRadius: BorderRadius.circular(15),
        onTap: onTap,
        child: SizedBox(
          width: 45,
          height: 45,
          child: Icon(icon, size: 20, color: const Color(0xFF234E50)),
        ),
      ),
    );
  }
}

// =================================================================
// USER LOCATION MARKER
// =================================================================

class _UserLocationMarker extends StatelessWidget {
  const _UserLocationMarker();

  @override
  Widget build(BuildContext context) {
    return Stack(
      alignment: Alignment.center,
      children: [
        Container(
          width: 48,
          height: 48,
          decoration: BoxDecoration(
            shape: BoxShape.circle,
            color: const Color(0xFF5C9F90).withValues(alpha: .15),
          ),
        ),

        Container(
          width: 19,
          height: 19,
          decoration: BoxDecoration(
            shape: BoxShape.circle,
            color: const Color(0xFF326E65),
            border: Border.all(color: Colors.white, width: 3),
            boxShadow: [
              BoxShadow(
                color: Colors.black.withValues(alpha: .18),
                blurRadius: 7,
              ),
            ],
          ),
        ),
      ],
    );
  }
}

// =================================================================
// PFZ MARKER
// =================================================================

class _PFZMarker extends StatelessWidget {
  final String level;
  final double score;

  const _PFZMarker({required this.level, required this.score});

  Color get color {
    switch (level.toUpperCase()) {
      case 'HIGH':
        return const Color(0xFF3F8A70);

      case 'MODERATE':
        return const Color(0xFFD49A45);

      default:
        return const Color(0xFF7C9AA0);
    }
  }

  @override
  Widget build(BuildContext context) {
    return Stack(
      alignment: Alignment.center,
      children: [
        Container(
          width: 62,
          height: 62,
          decoration: BoxDecoration(
            shape: BoxShape.circle,
            color: color.withValues(alpha: .13),
            border: Border.all(color: color.withValues(alpha: .45), width: 1),
          ),
        ),

        Container(
          width: 43,
          height: 43,
          decoration: BoxDecoration(
            shape: BoxShape.circle,
            color: Colors.white,
            border: Border.all(color: color, width: 2),
            boxShadow: [
              BoxShadow(color: color.withValues(alpha: .18), blurRadius: 9),
            ],
          ),
          child: Column(
            mainAxisAlignment: MainAxisAlignment.center,
            children: [
              Icon(Icons.phishing_outlined, size: 16, color: color),

              Text(
                score.toStringAsFixed(0),
                style: TextStyle(
                  fontSize: 8,
                  fontWeight: FontWeight.w800,
                  color: color,
                ),
              ),
            ],
          ),
        ),
      ],
    );
  }
}
