import 'dart:async';
import 'dart:convert';
import 'dart:math' as math;
import 'dart:ui' as ui;

import 'package:flutter/material.dart';
import 'package:flutter_map/flutter_map.dart';
import 'package:frontend/login_page.dart';
import 'package:geolocator/geolocator.dart';
import 'package:http/http.dart' as http;
import 'package:latlong2/latlong.dart';
import 'explore_page.dart';

void main() {
  runApp(const MarineIntelligenceApp());
}

// ============================================================================
// APP
// ============================================================================

class MarineIntelligenceApp extends StatelessWidget {
  const MarineIntelligenceApp({super.key});

  @override
  Widget build(BuildContext context) {
    return MaterialApp(
      debugShowCheckedModeBanner: false,
      title: 'Marine Intelligence',
      theme: ThemeData(
        useMaterial3: true,
        scaffoldBackgroundColor: const Color(0xFFF3F6F1),
        fontFamily: 'sans-serif',
        colorScheme: ColorScheme.fromSeed(seedColor: const Color(0xFF285B5B)),
      ),
      home: const LoginPage(nextPage: MarineHome(userName: 'Guest')),
    );
  }
}

// ============================================================================
// MARINE DATA
// ============================================================================

class MarineData {
  final double latitude;
  final double longitude;

  final double waveHeight;
  final double waveDirection;
  final double wavePeriod;

  final double waterTemperature;

  final double windSpeed;
  final double windDirection;

  final double precipitation;

  final double risk;

  MarineData({
    required this.latitude,
    required this.longitude,
    required this.waveHeight,
    required this.waveDirection,
    required this.wavePeriod,
    required this.waterTemperature,
    required this.windSpeed,
    required this.windDirection,
    required this.precipitation,
    required this.risk,
  });

  String get riskLabel {
    if (risk < 30) {
      return 'CALM';
    }

    if (risk < 60) {
      return 'MODERATE';
    }

    return 'HIGH';
  }

  String get riskDescription {
    if (risk < 30) {
      return 'Conditions are within a relatively calm range.';
    }

    if (risk < 60) {
      return 'Some marine conditions require attention before departure.';
    }

    return 'Marine conditions indicate increased caution is required.';
  }
}

// ============================================================================
// LOCATION SERVICE
// ============================================================================

class LocationService {
  static Future<Position> getCurrentLocation() async {
    bool serviceEnabled = await Geolocator.isLocationServiceEnabled();

    if (!serviceEnabled) {
      throw Exception('Location services are disabled.');
    }

    LocationPermission permission = await Geolocator.checkPermission();

    if (permission == LocationPermission.denied) {
      permission = await Geolocator.requestPermission();
    }

    if (permission == LocationPermission.denied) {
      throw Exception('Location permission was denied.');
    }

    if (permission == LocationPermission.deniedForever) {
      throw Exception(
        'Location permission is permanently denied. Enable it from Settings.',
      );
    }

    return Geolocator.getCurrentPosition(
      locationSettings: const LocationSettings(accuracy: LocationAccuracy.high),
    );
  }
}

// ============================================================================
// MARINE API SERVICE
// ============================================================================

class MarineService {
  static Future<MarineData> getMarineData(
    double latitude,
    double longitude,
  ) async {
    final marineUri = Uri.parse(
      'https://marine-api.open-meteo.com/v1/marine'
      '?latitude=$latitude'
      '&longitude=$longitude'
      '&current=wave_height,wave_direction,wave_period,sea_surface_temperature'
      '&timezone=auto',
    );

    final weatherUri = Uri.parse(
      'https://api.open-meteo.com/v1/forecast'
      '?latitude=$latitude'
      '&longitude=$longitude'
      '&current=wind_speed_10m,wind_direction_10m,precipitation'
      '&timezone=auto',
    );

    final responses = await Future.wait([
      http.get(marineUri),
      http.get(weatherUri),
    ]);

    final marineResponse = responses[0];
    final weatherResponse = responses[1];

    if (marineResponse.statusCode != 200) {
      throw Exception('Marine data unavailable.');
    }

    if (weatherResponse.statusCode != 200) {
      throw Exception('Weather data unavailable.');
    }

    final marineJson = jsonDecode(marineResponse.body);

    final weatherJson = jsonDecode(weatherResponse.body);

    final marineCurrent = marineJson['current'] ?? {};

    final weatherCurrent = weatherJson['current'] ?? {};

    final waveHeight = _number(marineCurrent['wave_height']);

    final waveDirection = _number(marineCurrent['wave_direction']);

    final wavePeriod = _number(marineCurrent['wave_period']);

    final waterTemperature = _number(marineCurrent['sea_surface_temperature']);

    final windSpeed = _number(weatherCurrent['wind_speed_10m']);

    final windDirection = _number(weatherCurrent['wind_direction_10m']);

    final precipitation = _number(weatherCurrent['precipitation']);

    final risk = RiskEngine.calculate(
      waveHeight: waveHeight,
      windSpeed: windSpeed,
      precipitation: precipitation,
    );

    return MarineData(
      latitude: latitude,
      longitude: longitude,
      waveHeight: waveHeight,
      waveDirection: waveDirection,
      wavePeriod: wavePeriod,
      waterTemperature: waterTemperature,
      windSpeed: windSpeed,
      windDirection: windDirection,
      precipitation: precipitation,
      risk: risk,
    );
  }

  static double _number(dynamic value) {
    if (value == null) {
      return 0;
    }

    if (value is num) {
      return value.toDouble();
    }

    return double.tryParse(value.toString()) ?? 0;
  }
}

// ============================================================================
// RISK ENGINE
// ============================================================================

class RiskEngine {
  static double calculate({
    required double waveHeight,
    required double windSpeed,
    required double precipitation,
  }) {
    double risk = 0;

    // WAVE
    if (waveHeight >= 3.0) {
      risk += 45;
    } else if (waveHeight >= 2.0) {
      risk += 30;
    } else if (waveHeight >= 1.2) {
      risk += 18;
    } else if (waveHeight >= 0.7) {
      risk += 8;
    }

    // WIND
    if (windSpeed >= 45) {
      risk += 35;
    } else if (windSpeed >= 30) {
      risk += 25;
    } else if (windSpeed >= 20) {
      risk += 15;
    } else if (windSpeed >= 12) {
      risk += 7;
    }

    // RAIN
    if (precipitation >= 10) {
      risk += 20;
    } else if (precipitation >= 5) {
      risk += 12;
    } else if (precipitation > 0) {
      risk += 5;
    }

    return risk.clamp(0, 100);
  }
}

// ============================================================================
// MAIN HOME
// ============================================================================

class MarineHome extends StatefulWidget {
  final String userName;

  const MarineHome({super.key, required this.userName});

  @override
  State<MarineHome> createState() => _MarineHomeState();
}

class _MarineHomeState extends State<MarineHome>
    with SingleTickerProviderStateMixin {
  late AnimationController _animationController;

  MarineData? marineData;

  Position? position;

  bool loading = true;

  String? error;

  int selectedNavigation = 0;

  int selectedSeaAction = 0;

  StreamSubscription<Position>? positionSubscription;

  final List<String> seaActions = [
    'Tomorrow',
    'Fishing',
    'Safe route',
    'Sea safety',
  ];

  @override
  void initState() {
    super.initState();

    _animationController = AnimationController(
      vsync: this,
      duration: const Duration(seconds: 10),
    )..repeat();

    _loadLiveData();
  }

  @override
  void dispose() {
    _animationController.dispose();
    positionSubscription?.cancel();
    super.dispose();
  }

  String _getGreeting() {
    final hour = DateTime.now().hour;

    if (hour >= 5 && hour < 12) {
      return 'GOOD MORNING';
    } else if (hour >= 12 && hour < 17) {
      return 'GOOD AFTERNOON';
    } else if (hour >= 17 && hour < 21) {
      return 'GOOD EVENING';
    } else {
      return 'GOOD NIGHT';
    }
  }
  // ==========================================================================
  // LOAD LIVE DATA
  // ==========================================================================

  Future<void> _loadLiveData() async {
    setState(() {
      loading = true;
      error = null;
    });

    try {
      final currentPosition = await LocationService.getCurrentLocation();

      final data = await MarineService.getMarineData(
        currentPosition.latitude,
        currentPosition.longitude,
      );

      if (!mounted) {
        return;
      }

      setState(() {
        position = currentPosition;
        marineData = data;
        loading = false;
      });
    } catch (e) {
      if (!mounted) {
        return;
      }

      setState(() {
        loading = false;

        error = e.toString().replaceFirst('Exception: ', '');
      });
    }
  }

  // ==========================================================================
  // BUILD
  // ==========================================================================

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      backgroundColor: const Color(0xFFF3F6F1),
      body: SafeArea(
        child: IndexedStack(
          index: selectedNavigation,
          children: [
            _homePage(),
            _explorePage(),
            _assistantPage(),
            _journeyPage(),
            _profilePage(),
          ],
        ),
      ),
    );
  }

  // ==========================================================================
  // HOME PAGE
  // ==========================================================================

  Widget _homePage() {
    return Stack(
      children: [
        RefreshIndicator(
          onRefresh: _loadLiveData,
          child: CustomScrollView(
            physics: const BouncingScrollPhysics(
              parent: AlwaysScrollableScrollPhysics(),
            ),
            slivers: [
              SliverToBoxAdapter(child: _header()),
              SliverToBoxAdapter(child: _seaScene()),
              SliverToBoxAdapter(child: _seaPulse()),
              SliverToBoxAdapter(child: _talkToSea()),
              SliverToBoxAdapter(child: _boatStatus()),
              const SliverToBoxAdapter(child: SizedBox(height: 110)),
            ],
          ),
        ),
        Positioned(left: 18, right: 18, bottom: 18, child: _bottomNavigation()),
      ],
    );
  }

  // ==========================================================================
  // HEADER
  // ==========================================================================

  Widget _header() {
    return Padding(
      padding: const EdgeInsets.fromLTRB(22, 18, 22, 12),
      child: Row(
        children: [
          Expanded(
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Text(
                  _getGreeting(),
                  style: TextStyle(
                    fontSize: 10,
                    letterSpacing: 2.2,
                    fontWeight: FontWeight.w700,
                    color: Color(0xFF718080),
                  ),
                ),
                SizedBox(height: 5),
                Text(
                  widget.userName,
                  style: TextStyle(
                    fontSize: 28,
                    fontWeight: FontWeight.w700,
                    color: Color(0xFF183B3D),
                  ),
                ),
              ],
            ),
          ),

          GestureDetector(
            onTap: _loadLiveData,
            child: Container(
              width: 45,
              height: 45,
              decoration: BoxDecoration(
                color: Colors.white,
                borderRadius: BorderRadius.circular(16),
              ),
              child: loading
                  ? const Padding(
                      padding: EdgeInsets.all(13),
                      child: CircularProgressIndicator(
                        strokeWidth: 2,
                        color: Color(0xFF285B5B),
                      ),
                    )
                  : const Icon(Icons.refresh_rounded, color: Color(0xFF28585A)),
            ),
          ),

          const SizedBox(width: 8),

          Container(
            width: 45,
            height: 45,
            decoration: BoxDecoration(
              color: const Color(0xFF234E50),
              borderRadius: BorderRadius.circular(16),
            ),
            child: const Center(
              child: Text(
                'M',
                style: TextStyle(
                  color: Colors.white,
                  fontWeight: FontWeight.w700,
                  fontSize: 16,
                ),
              ),
            ),
          ),
        ],
      ),
    );
  }

  // ==========================================================================
  // SEA SCENE
  // ==========================================================================

  Widget _seaScene() {
    return Padding(
      padding: const EdgeInsets.symmetric(horizontal: 18),
      child: ClipRRect(
        borderRadius: BorderRadius.circular(34),
        child: SizedBox(
          height: 405,
          child: AnimatedBuilder(
            animation: _animationController,
            builder: (context, child) {
              return CustomPaint(
                painter: SeaPainter(progress: _animationController.value),
                child: child,
              );
            },
            child: _seaContent(marineData),
          ),
        ),
      ),
    );
  }

  Widget _seaContent(MarineData? data) {
    return Padding(
      padding: const EdgeInsets.fromLTRB(24, 23, 24, 23),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Row(
            children: [
              Container(
                padding: const EdgeInsets.symmetric(
                  horizontal: 10,
                  vertical: 6,
                ),
                decoration: BoxDecoration(
                  color: Colors.white.withValues(alpha: .09),
                  borderRadius: BorderRadius.circular(20),
                ),
                child: const Row(
                  children: [
                    Icon(Icons.circle, size: 6, color: Color(0xFF9ED5C8)),
                    SizedBox(width: 6),
                    Text(
                      'LIVE',
                      style: TextStyle(
                        color: Colors.white,
                        fontSize: 9,
                        letterSpacing: 1.5,
                        fontWeight: FontWeight.w700,
                      ),
                    ),
                  ],
                ),
              ),

              const Spacer(),

              Text(
                _currentTime(),
                style: TextStyle(
                  color: Colors.white.withValues(alpha: .55),
                  fontSize: 9,
                  letterSpacing: 1,
                ),
              ),
            ],
          ),

          const Spacer(flex: 3),

          Padding(
            padding: const EdgeInsets.only(bottom: 75),
            child: Text(
              loading
                  ? 'Reading the\nsea around you.'
                  : data == null
                  ? 'The sea is\nwaiting.'
                  : data.riskLabel == 'CALM'
                  ? 'The sea is\nquiet here.'
                  : 'The sea is\nchanging.',
              style: const TextStyle(
                color: Color(0xFFF4F3E9),
                fontSize: 36,
                height: 1.02,
                fontWeight: FontWeight.w600,
                letterSpacing: -1,
              ),
            ),
          ),

          const SizedBox(height: 10),

          Text(
            error ??
                data?.riskDescription ??
                'Connecting to live marine conditions...',
            style: TextStyle(
              color: Colors.white.withValues(alpha: .66),
              fontSize: 13,
              height: 1.45,
            ),
          ),

          const SizedBox(height: 24),

          Row(
            children: [
              _seaReading(
                'WAVE',
                data == null ? '--' : '${data.waveHeight.toStringAsFixed(1)} m',
              ),
              _verticalDivider(),
              _seaReading(
                'WIND',
                data == null
                    ? '--'
                    : '${data.windSpeed.toStringAsFixed(0)} km/h',
              ),
              _verticalDivider(),
              _seaReading(
                'WATER',
                data == null
                    ? '--'
                    : '${data.waterTemperature.toStringAsFixed(1)}°C',
              ),
            ],
          ),

          const SizedBox(height: 20),

          Row(
            children: [
              const Icon(
                Icons.navigation_outlined,
                size: 16,
                color: Color(0xFFA5D7C9),
              ),
              const SizedBox(width: 7),
              Expanded(
                child: Text(
                  data == null
                      ? 'Waiting for GPS...'
                      : '${data.latitude.toStringAsFixed(4)}° N   '
                            '${data.longitude.toStringAsFixed(4)}° E',
                  style: TextStyle(
                    color: Colors.white.withValues(alpha: .62),
                    fontSize: 11,
                    letterSpacing: .3,
                  ),
                ),
              ),
            ],
          ),
        ],
      ),
    );
  }

  String _currentTime() {
    final now = DateTime.now();

    final hour = now.hour.toString().padLeft(2, '0');

    final minute = now.minute.toString().padLeft(2, '0');

    return '${now.day.toString().padLeft(2, '0')} '
        '${_month(now.month)} • $hour:$minute';
  }

  String _month(int month) {
    const months = [
      'JAN',
      'FEB',
      'MAR',
      'APR',
      'MAY',
      'JUN',
      'JUL',
      'AUG',
      'SEP',
      'OCT',
      'NOV',
      'DEC',
    ];

    return months[month - 1];
  }

  Widget _seaReading(String title, String value) {
    return Expanded(
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Text(
            title,
            style: TextStyle(
              color: Colors.white.withValues(alpha: .42),
              fontSize: 9,
              letterSpacing: 1.5,
              fontWeight: FontWeight.w600,
            ),
          ),
          const SizedBox(height: 5),
          Text(
            value,
            style: const TextStyle(
              color: Colors.white,
              fontSize: 16,
              fontWeight: FontWeight.w600,
            ),
          ),
        ],
      ),
    );
  }

  Widget _verticalDivider() {
    return Container(
      width: 1,
      height: 30,
      color: Colors.white.withValues(alpha: .10),
      margin: const EdgeInsets.symmetric(horizontal: 12),
    );
  }

  // ==========================================================================
  // SEA PULSE
  // ==========================================================================

  Widget _seaPulse() {
    final data = marineData;

    final risk = data?.risk ?? 0;

    return Padding(
      padding: const EdgeInsets.fromLTRB(22, 27, 22, 0),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Row(
            children: [
              const Expanded(
                child: Text(
                  'Sea pulse',
                  style: TextStyle(
                    fontSize: 22,
                    fontWeight: FontWeight.w700,
                    color: Color(0xFF183B3D),
                  ),
                ),
              ),
              Text(
                'LIVE',
                style: TextStyle(
                  fontSize: 9,
                  letterSpacing: 1.5,
                  fontWeight: FontWeight.w700,
                  color: Colors.grey.shade500,
                ),
              ),
            ],
          ),

          const SizedBox(height: 14),

          Container(
            height: 205,
            decoration: BoxDecoration(
              color: Colors.white,
              borderRadius: BorderRadius.circular(29),
              boxShadow: [
                BoxShadow(
                  color: const Color(0xFF183B3D).withValues(alpha: .055),
                  blurRadius: 25,
                  offset: const Offset(0, 10),
                ),
              ],
            ),
            child: Row(
              children: [
                Expanded(
                  flex: 5,
                  child: Center(
                    child: SizedBox(
                      width: 165,
                      height: 165,
                      child: CustomPaint(
                        painter: PulsePainter(risk: risk),
                        child: Center(
                          child: Column(
                            mainAxisSize: MainAxisSize.min,
                            children: [
                              Text(
                                '${risk.toStringAsFixed(0)}%',
                                style: const TextStyle(
                                  fontSize: 30,
                                  fontWeight: FontWeight.w700,
                                  color: Color(0xFF244F50),
                                ),
                              ),
                              Text(
                                'SEA RISK',
                                style: TextStyle(
                                  fontSize: 9,
                                  letterSpacing: 1.4,
                                  color: Colors.grey.shade500,
                                  fontWeight: FontWeight.w700,
                                ),
                              ),
                            ],
                          ),
                        ),
                      ),
                    ),
                  ),
                ),

                Expanded(
                  flex: 5,
                  child: Padding(
                    padding: const EdgeInsets.only(right: 20),
                    child: Column(
                      mainAxisAlignment: MainAxisAlignment.center,
                      crossAxisAlignment: CrossAxisAlignment.start,
                      children: [
                        Text(
                          data?.riskLabel ?? 'WAITING',
                          style: const TextStyle(
                            fontSize: 11,
                            letterSpacing: 1.8,
                            color: Color(0xFF4B8178),
                            fontWeight: FontWeight.w700,
                          ),
                        ),

                        const SizedBox(height: 9),

                        Text(
                          data?.riskDescription ??
                              'Getting live marine conditions...',
                          style: const TextStyle(
                            fontSize: 13,
                            height: 1.45,
                            color: Color(0xFF39595A),
                          ),
                        ),

                        const SizedBox(height: 15),

                        Row(
                          children: [
                            _tinyIndicator(
                              'Wind',
                              data == null
                                  ? '--'
                                  : data.windSpeed.toStringAsFixed(0),
                            ),
                            const SizedBox(width: 15),
                            _tinyIndicator(
                              'Wave',
                              data == null
                                  ? '--'
                                  : data.waveHeight.toStringAsFixed(1),
                            ),
                          ],
                        ),
                      ],
                    ),
                  ),
                ),
              ],
            ),
          ),
        ],
      ),
    );
  }

  Widget _tinyIndicator(String title, String value) {
    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        Text(
          value,
          style: const TextStyle(
            fontSize: 14,
            fontWeight: FontWeight.w700,
            color: Color(0xFF244F50),
          ),
        ),
        const SizedBox(height: 2),
        Text(title, style: TextStyle(fontSize: 9, color: Colors.grey.shade500)),
      ],
    );
  }

  // ==========================================================================
  // TALK TO SEA
  // ==========================================================================

  Widget _talkToSea() {
    return Padding(
      padding: const EdgeInsets.fromLTRB(22, 27, 22, 0),
      child: Container(
        padding: const EdgeInsets.fromLTRB(19, 19, 19, 18),
        decoration: BoxDecoration(
          color: const Color(0xFFE5EFEA),
          borderRadius: BorderRadius.circular(28),
        ),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            const Row(
              children: [
                Icon(Icons.forum_outlined, size: 21, color: Color(0xFF376E68)),
                SizedBox(width: 11),
                Text(
                  'Talk to the sea',
                  style: TextStyle(
                    fontWeight: FontWeight.w700,
                    fontSize: 16,
                    color: Color(0xFF234F50),
                  ),
                ),
              ],
            ),

            const SizedBox(height: 14),

            const Text(
              'What are you planning?',
              style: TextStyle(fontSize: 13, color: Color(0xFF426160)),
            ),

            const SizedBox(height: 12),

            SizedBox(
              height: 39,
              child: ListView.builder(
                scrollDirection: Axis.horizontal,
                itemCount: seaActions.length,
                itemBuilder: (context, index) {
                  final selected = selectedSeaAction == index;

                  return GestureDetector(
                    onTap: () {
                      setState(() {
                        selectedSeaAction = index;
                      });
                    },
                    child: AnimatedContainer(
                      duration: const Duration(milliseconds: 220),
                      margin: const EdgeInsets.only(right: 8),
                      padding: const EdgeInsets.symmetric(horizontal: 15),
                      decoration: BoxDecoration(
                        color: selected
                            ? const Color(0xFF285B5B)
                            : Colors.white.withValues(alpha: .72),
                        borderRadius: BorderRadius.circular(20),
                      ),
                      child: Center(
                        child: Text(
                          seaActions[index],
                          style: TextStyle(
                            fontSize: 11,
                            fontWeight: FontWeight.w600,
                            color: selected
                                ? Colors.white
                                : const Color(0xFF426160),
                          ),
                        ),
                      ),
                    ),
                  );
                },
              ),
            ),

            const SizedBox(height: 15),

            Text(
              _contextualMessage(),
              style: const TextStyle(
                fontSize: 12,
                height: 1.45,
                color: Color(0xFF426160),
              ),
            ),
          ],
        ),
      ),
    );
  }

  String _contextualMessage() {
    switch (selectedSeaAction) {
      case 1:
        return 'I can look for nearby fishing zones using sea temperature and ocean conditions.';

      case 2:
        return 'I can compare routes and keep known hazard areas out of your path.';

      case 3:
        return 'I can check wind, waves, rainfall and marine conditions before you leave.';

      default:
        return 'I can compare tomorrow morning with the conditions around your current location.';
    }
  }

  // ==========================================================================
  // BOAT STATUS
  // ==========================================================================

  Widget _boatStatus() {
    final data = marineData;

    return Padding(
      padding: const EdgeInsets.fromLTRB(22, 27, 22, 0),
      child: Row(
        children: [
          Expanded(
            child: _boatTile(
              icon: Icons.sailing_outlined,
              title: 'SEA EXPLORER',
              subtitle: 'Marine data connected',
              color: const Color(0xFFE7EEE8),
            ),
          ),

          const SizedBox(width: 10),

          Expanded(
            child: _boatTile(
              icon: Icons.gps_fixed,
              title: 'GPS',
              subtitle: data == null
                  ? 'Waiting...'
                  : '${data.latitude.toStringAsFixed(4)} / '
                        '${data.longitude.toStringAsFixed(4)}',
              color: const Color(0xFFF0E9DA),
            ),
          ),
        ],
      ),
    );
  }

  Widget _boatTile({
    required IconData icon,
    required String title,
    required String subtitle,
    required Color color,
  }) {
    return Container(
      padding: const EdgeInsets.all(15),
      decoration: BoxDecoration(
        color: Colors.white,
        borderRadius: BorderRadius.circular(22),
      ),
      child: Row(
        children: [
          Container(
            width: 38,
            height: 38,
            decoration: BoxDecoration(
              color: color,
              borderRadius: BorderRadius.circular(13),
            ),
            child: Icon(icon, size: 19, color: const Color(0xFF426C68)),
          ),

          const SizedBox(width: 10),

          Expanded(
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Text(
                  title,
                  overflow: TextOverflow.ellipsis,
                  style: const TextStyle(
                    fontSize: 10,
                    letterSpacing: .8,
                    fontWeight: FontWeight.w700,
                    color: Color(0xFF315757),
                  ),
                ),
                const SizedBox(height: 4),
                Text(
                  subtitle,
                  overflow: TextOverflow.ellipsis,
                  style: TextStyle(fontSize: 9, color: Colors.grey.shade500),
                ),
              ],
            ),
          ),
        ],
      ),
    );
  }

  // ==========================================================================
  // EXPLORE
  // ==========================================================================

  Widget _explorePage() {
    final data = marineData;

    final center = data == null
        ? const LatLng(18.5204, 73.8567)
        : LatLng(data.latitude, data.longitude);

    return Stack(
      children: [
        Column(
          children: [
            _pageHeader('Explore', 'Your sea around you'),

            Expanded(
              child: FlutterMap(
                options: MapOptions(initialCenter: center, initialZoom: 10),
                children: [
                  TileLayer(
                    urlTemplate:
                        'https://tile.openstreetmap.org/{z}/{x}/{y}.png',
                    userAgentPackageName: 'com.marineintelligence.app',
                  ),

                  if (data != null)
                    MarkerLayer(
                      markers: [
                        Marker(
                          point: center,
                          width: 60,
                          height: 60,
                          child: Container(
                            decoration: BoxDecoration(
                              color: const Color(0xFF285B5B),
                              shape: BoxShape.circle,
                              border: Border.all(color: Colors.white, width: 4),
                            ),
                            child: const Icon(
                              Icons.sailing,
                              color: Colors.white,
                            ),
                          ),
                        ),
                      ],
                    ),
                ],
              ),
            ),
          ],
        ),

        Positioned(left: 20, right: 20, bottom: 95, child: _mapInfoCard()),

        Positioned(left: 18, right: 18, bottom: 18, child: _bottomNavigation()),
      ],
    );
  }

  Widget _mapInfoCard() {
    final data = marineData;

    return Container(
      padding: const EdgeInsets.all(17),
      decoration: BoxDecoration(
        color: Colors.white.withValues(alpha: .96),
        borderRadius: BorderRadius.circular(23),
        boxShadow: const [BoxShadow(blurRadius: 25, color: Colors.black12)],
      ),
      child: Row(
        children: [
          Container(
            width: 43,
            height: 43,
            decoration: BoxDecoration(
              color: const Color(0xFFE5EFEA),
              borderRadius: BorderRadius.circular(14),
            ),
            child: const Icon(Icons.water, color: Color(0xFF285B5B)),
          ),

          const SizedBox(width: 12),

          Expanded(
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Text(
                  data == null
                      ? 'Waiting for marine data'
                      : '${data.riskLabel} CONDITIONS',
                  style: const TextStyle(
                    fontSize: 11,
                    letterSpacing: 1,
                    fontWeight: FontWeight.w700,
                    color: Color(0xFF285B5B),
                  ),
                ),

                const SizedBox(height: 4),

                Text(
                  data == null
                      ? 'Enable location to explore your area.'
                      : '${data.waveHeight.toStringAsFixed(1)} m waves • '
                            '${data.windSpeed.toStringAsFixed(0)} km/h wind',
                  style: const TextStyle(
                    fontSize: 12,
                    color: Color(0xFF526565),
                  ),
                ),
              ],
            ),
          ),
        ],
      ),
    );
  }

  // ==========================================================================
  // ASSISTANT
  // ==========================================================================

  Widget _assistantPage() {
    final data = marineData;

    return Stack(
      children: [
        Column(
          children: [
            _pageHeader('Talk to the Sea', 'Ask about your marine conditions'),

            Expanded(
              child: ListView(
                padding: const EdgeInsets.fromLTRB(22, 15, 22, 120),
                children: [
                  _assistantBubble(
                    'I am connected to your current marine conditions. Choose something you want to know.',
                    false,
                  ),

                  const SizedBox(height: 14),

                  _questionButton(
                    'Is it safe to go out?',
                    Icons.shield_outlined,
                  ),

                  _questionButton('How are the waves?', Icons.waves_outlined),

                  _questionButton('What is the wind like?', Icons.air),

                  _questionButton(
                    'Show my current position',
                    Icons.location_on_outlined,
                  ),

                  const SizedBox(height: 20),

                  if (data != null)
                    Container(
                      padding: const EdgeInsets.all(20),
                      decoration: BoxDecoration(
                        color: const Color(0xFFE5EFEA),
                        borderRadius: BorderRadius.circular(25),
                      ),
                      child: Text(
                        'Current reading: ${data.riskLabel}. '
                        'Wave height ${data.waveHeight.toStringAsFixed(1)} m, '
                        'wind ${data.windSpeed.toStringAsFixed(0)} km/h, '
                        'water temperature '
                        '${data.waterTemperature.toStringAsFixed(1)}°C.',
                        style: const TextStyle(
                          fontSize: 13,
                          height: 1.5,
                          color: Color(0xFF315757),
                        ),
                      ),
                    ),
                ],
              ),
            ),
          ],
        ),

        Positioned(left: 18, right: 18, bottom: 18, child: _bottomNavigation()),
      ],
    );
  }

  Widget _assistantBubble(String text, bool user) {
    return Align(
      alignment: user ? Alignment.centerRight : Alignment.centerLeft,
      child: Container(
        constraints: const BoxConstraints(maxWidth: 330),
        padding: const EdgeInsets.all(17),
        decoration: BoxDecoration(
          color: user ? const Color(0xFF285B5B) : Colors.white,
          borderRadius: BorderRadius.circular(22),
        ),
        child: Text(
          text,
          style: TextStyle(
            fontSize: 13,
            height: 1.45,
            color: user ? Colors.white : const Color(0xFF315757),
          ),
        ),
      ),
    );
  }

  Widget _questionButton(String text, IconData icon) {
    return GestureDetector(
      onTap: () {
        _showAssistantAnswer(text);
      },
      child: Container(
        margin: const EdgeInsets.only(bottom: 10),
        padding: const EdgeInsets.all(16),
        decoration: BoxDecoration(
          color: Colors.white,
          borderRadius: BorderRadius.circular(19),
        ),
        child: Row(
          children: [
            Icon(icon, color: const Color(0xFF376E68)),
            const SizedBox(width: 13),
            Expanded(
              child: Text(
                text,
                style: const TextStyle(
                  fontSize: 13,
                  fontWeight: FontWeight.w600,
                  color: Color(0xFF315757),
                ),
              ),
            ),
            const Icon(Icons.chevron_right, color: Colors.grey),
          ],
        ),
      ),
    );
  }

  void _showAssistantAnswer(String question) {
    final data = marineData;

    String answer;

    if (data == null) {
      answer = 'I need your live location and marine data first.';
    } else if (question.contains('safe')) {
      answer =
          'Current calculated marine risk is '
          '${data.risk.toStringAsFixed(0)}%, classified as '
          '${data.riskLabel}. '
          'Wave height is ${data.waveHeight.toStringAsFixed(1)} m '
          'and wind is ${data.windSpeed.toStringAsFixed(0)} km/h.';
    } else if (question.contains('waves')) {
      answer =
          'Current wave height is '
          '${data.waveHeight.toStringAsFixed(1)} m. '
          'Wave period is ${data.wavePeriod.toStringAsFixed(1)} seconds.';
    } else if (question.contains('wind')) {
      answer =
          'Current wind speed is '
          '${data.windSpeed.toStringAsFixed(0)} km/h, '
          'with direction ${data.windDirection.toStringAsFixed(0)}°.';
    } else {
      answer =
          'Your current position is '
          '${data.latitude.toStringAsFixed(5)}, '
          '${data.longitude.toStringAsFixed(5)}.';
    }

    showModalBottomSheet(
      context: context,
      backgroundColor: const Color(0xFFF3F6F1),
      shape: const RoundedRectangleBorder(
        borderRadius: BorderRadius.vertical(top: Radius.circular(30)),
      ),
      builder: (context) {
        return Padding(
          padding: const EdgeInsets.fromLTRB(22, 25, 22, 35),
          child: Column(
            mainAxisSize: MainAxisSize.min,
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              const Text(
                'Sea intelligence',
                style: TextStyle(
                  fontSize: 21,
                  fontWeight: FontWeight.w700,
                  color: Color(0xFF183B3D),
                ),
              ),
              const SizedBox(height: 15),
              Text(
                answer,
                style: const TextStyle(
                  fontSize: 14,
                  height: 1.5,
                  color: Color(0xFF426160),
                ),
              ),
            ],
          ),
        );
      },
    );
  }

  // ==========================================================================
  // JOURNEY
  // ==========================================================================

  Widget _journeyPage() {
    return Stack(
      children: [
        Column(
          children: [
            _pageHeader('Journey', 'Track your movement on the sea'),

            Expanded(child: JourneyTracker(initialPosition: position)),
          ],
        ),

        Positioned(left: 18, right: 18, bottom: 18, child: _bottomNavigation()),
      ],
    );
  }

  // ==========================================================================
  // PROFILE
  // ==========================================================================

  Widget _profilePage() {
    final data = marineData;

    return Stack(
      children: [
        ListView(
          padding: const EdgeInsets.fromLTRB(22, 20, 22, 110),
          children: [
            const Text(
              'Me',
              style: TextStyle(
                fontSize: 29,
                fontWeight: FontWeight.w700,
                color: Color(0xFF183B3D),
              ),
            ),

            const SizedBox(height: 6),

            Text(
              'Your marine profile',
              style: TextStyle(fontSize: 13, color: Colors.grey.shade600),
            ),

            const SizedBox(height: 25),

            Container(
              padding: const EdgeInsets.all(20),
              decoration: BoxDecoration(
                color: const Color(0xFF234E50),
                borderRadius: BorderRadius.circular(28),
              ),
              child: const Row(
                children: [
                  CircleAvatar(
                    radius: 31,
                    backgroundColor: Color(0xFFA3D6C8),
                    child: Text(
                      'M',
                      style: TextStyle(
                        color: Color(0xFF183B3D),
                        fontSize: 22,
                        fontWeight: FontWeight.w700,
                      ),
                    ),
                  ),
                  SizedBox(width: 15),
                  Column(
                    crossAxisAlignment: CrossAxisAlignment.start,
                    children: [
                      Text(
                        'Manisha',
                        style: TextStyle(
                          color: Colors.white,
                          fontSize: 20,
                          fontWeight: FontWeight.w700,
                        ),
                      ),
                      SizedBox(height: 5),
                      Text(
                        'Fisherman',
                        style: TextStyle(color: Colors.white60, fontSize: 12),
                      ),
                    ],
                  ),
                ],
              ),
            ),

            const SizedBox(height: 18),

            _profileItem(Icons.language, 'Language', 'English'),

            _profileItem(Icons.sailing, 'Boat', 'Sea Explorer'),

            _profileItem(
              Icons.location_on_outlined,
              'Current position',
              data == null
                  ? 'Unavailable'
                  : '${data.latitude.toStringAsFixed(4)}, '
                        '${data.longitude.toStringAsFixed(4)}',
            ),

            _profileItem(
              Icons.water_outlined,
              'Current sea state',
              data?.riskLabel ?? 'Waiting',
            ),

            const SizedBox(height: 20),

            GestureDetector(
              onTap: _loadLiveData,
              child: Container(
                padding: const EdgeInsets.all(17),
                decoration: BoxDecoration(
                  color: const Color(0xFFE5EFEA),
                  borderRadius: BorderRadius.circular(20),
                ),
                child: const Row(
                  children: [
                    Icon(Icons.sync, color: Color(0xFF285B5B)),
                    SizedBox(width: 12),
                    Text(
                      'Refresh marine intelligence',
                      style: TextStyle(
                        fontWeight: FontWeight.w600,
                        color: Color(0xFF315757),
                      ),
                    ),
                  ],
                ),
              ),
            ),
          ],
        ),

        Positioned(left: 18, right: 18, bottom: 18, child: _bottomNavigation()),
      ],
    );
  }

  Widget _profileItem(IconData icon, String title, String value) {
    return Container(
      margin: const EdgeInsets.only(bottom: 10),
      padding: const EdgeInsets.all(17),
      decoration: BoxDecoration(
        color: Colors.white,
        borderRadius: BorderRadius.circular(20),
      ),
      child: Row(
        children: [
          Container(
            width: 42,
            height: 42,
            decoration: BoxDecoration(
              color: const Color(0xFFE5EFEA),
              borderRadius: BorderRadius.circular(13),
            ),
            child: Icon(icon, color: const Color(0xFF376E68)),
          ),
          const SizedBox(width: 13),
          Expanded(
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Text(
                  title,
                  style: TextStyle(fontSize: 10, color: Colors.grey.shade500),
                ),
                const SizedBox(height: 4),
                Text(
                  value,
                  style: const TextStyle(
                    fontSize: 13,
                    fontWeight: FontWeight.w600,
                    color: Color(0xFF315757),
                  ),
                ),
              ],
            ),
          ),
        ],
      ),
    );
  }

  // ==========================================================================
  // PAGE HEADER
  // ==========================================================================

  Widget _pageHeader(String title, String subtitle) {
    return Padding(
      padding: const EdgeInsets.fromLTRB(22, 20, 22, 15),
      child: Row(
        children: [
          Expanded(
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Text(
                  title,
                  style: const TextStyle(
                    fontSize: 28,
                    fontWeight: FontWeight.w700,
                    color: Color(0xFF183B3D),
                  ),
                ),
                const SizedBox(height: 4),
                Text(
                  subtitle,
                  style: TextStyle(fontSize: 12, color: Colors.grey.shade600),
                ),
              ],
            ),
          ),

          GestureDetector(
            onTap: _loadLiveData,
            child: Container(
              width: 44,
              height: 44,
              decoration: BoxDecoration(
                color: Colors.white,
                borderRadius: BorderRadius.circular(15),
              ),
              child: const Icon(Icons.refresh, color: Color(0xFF285B5B)),
            ),
          ),
        ],
      ),
    );
  }

  // ==========================================================================
  // BOTTOM NAVIGATION
  // ==========================================================================

  Widget _bottomNavigation() {
    return Container(
      height: 69,
      padding: const EdgeInsets.symmetric(horizontal: 8),
      decoration: BoxDecoration(
        color: const Color(0xFF183B3D),
        borderRadius: BorderRadius.circular(27),
        boxShadow: [
          BoxShadow(
            color: const Color(0xFF183B3D).withValues(alpha: .20),
            blurRadius: 28,
            offset: const Offset(0, 11),
          ),
        ],
      ),
      child: Row(
        children: [
          _nav(Icons.water_outlined, 'Sea', 0),

          _nav(Icons.explore_outlined, 'Explore', 1),

          Expanded(
            child: Center(
              child: GestureDetector(
                onTap: () {
                  setState(() {
                    selectedNavigation = 2;
                  });
                },
                child: Container(
                  width: 50,
                  height: 50,
                  decoration: const BoxDecoration(
                    color: Color(0xFFA3D6C8),
                    shape: BoxShape.circle,
                  ),
                  child: const Icon(
                    Icons.forum_outlined,
                    color: Color(0xFF183B3D),
                    size: 22,
                  ),
                ),
              ),
            ),
          ),

          _nav(Icons.alt_route_rounded, 'Journey', 3),

          _nav(Icons.person_outline, 'Me', 4),
        ],
      ),
    );
  }

  Widget _nav(IconData icon, String label, int index) {
    final active = selectedNavigation == index;

    return Expanded(
      child: GestureDetector(
        onTap: () {
          if (index == 1) {
            Navigator.push(
              context,
              MaterialPageRoute(
                builder: (context) => ExplorePage(
                  latitude: marineData?.latitude,
                  longitude: marineData?.longitude,
                ),
              ),
            );
            return;
          }

          setState(() {
            selectedNavigation = index;
          });
        },
        child: Column(
          mainAxisAlignment: MainAxisAlignment.center,
          children: [
            Icon(
              icon,
              size: 20,
              color: active
                  ? const Color(0xFFA3D6C8)
                  : Colors.white.withValues(alpha: .42),
            ),
            const SizedBox(height: 4),
            Text(
              label,
              style: TextStyle(
                fontSize: 9,
                color: active
                    ? const Color(0xFFA3D6C8)
                    : Colors.white.withValues(alpha: .42),
                fontWeight: active ? FontWeight.w700 : FontWeight.normal,
              ),
            ),
          ],
        ),
      ),
    );
  }
}

// ============================================================================
// JOURNEY TRACKER
// ============================================================================

class JourneyTracker extends StatefulWidget {
  final Position? initialPosition;

  const JourneyTracker({super.key, required this.initialPosition});

  @override
  State<JourneyTracker> createState() => _JourneyTrackerState();
}

class _JourneyTrackerState extends State<JourneyTracker> {
  final List<LatLng> route = [];

  StreamSubscription<Position>? subscription;

  bool tracking = false;

  double distanceMeters = 0;

  Position? currentPosition;

  @override
  void initState() {
    super.initState();

    currentPosition = widget.initialPosition;

    if (currentPosition != null) {
      route.add(LatLng(currentPosition!.latitude, currentPosition!.longitude));
    }
  }

  @override
  void dispose() {
    subscription?.cancel();
    super.dispose();
  }

  Future<void> startTracking() async {
    try {
      LocationPermission permission = await Geolocator.checkPermission();

      if (permission == LocationPermission.denied) {
        permission = await Geolocator.requestPermission();

        if (permission == LocationPermission.denied) {
          throw Exception('Location permission denied.');
        }
      }

      setState(() {
        tracking = true;
        route.clear();
        distanceMeters = 0;
      });

      subscription =
          Geolocator.getPositionStream(
            locationSettings: const LocationSettings(
              accuracy: LocationAccuracy.high,
              distanceFilter: 5,
            ),
          ).listen((position) {
            if (!mounted) {
              return;
            }

            final point = LatLng(position.latitude, position.longitude);

            if (route.isNotEmpty) {
              final previous = route.last;

              final distance = Geolocator.distanceBetween(
                previous.latitude,
                previous.longitude,
                point.latitude,
                point.longitude,
              );

              distanceMeters += distance;
            }

            setState(() {
              currentPosition = position;

              route.add(point);
            });
          });
    } catch (e) {
      if (!mounted) {
        return;
      }

      ScaffoldMessenger.of(context).showSnackBar(
        SnackBar(content: Text(e.toString().replaceFirst('Exception: ', ''))),
      );
    }
  }

  void stopTracking() {
    subscription?.cancel();

    subscription = null;

    setState(() {
      tracking = false;
    });
  }

  @override
  Widget build(BuildContext context) {
    final center = currentPosition == null
        ? const LatLng(18.5204, 73.8567)
        : LatLng(currentPosition!.latitude, currentPosition!.longitude);

    return Stack(
      children: [
        FlutterMap(
          options: MapOptions(initialCenter: center, initialZoom: 15),
          children: [
            TileLayer(
              urlTemplate: 'https://tile.openstreetmap.org/{z}/{x}/{y}.png',
              userAgentPackageName: 'com.marineintelligence.app',
            ),

            if (route.length >= 2)
              PolylineLayer(
                polylines: [
                  Polyline(
                    points: route,
                    strokeWidth: 5,
                    color: const Color(0xFF285B5B),
                  ),
                ],
              ),

            if (currentPosition != null)
              MarkerLayer(
                markers: [
                  Marker(
                    point: center,
                    width: 55,
                    height: 55,
                    child: Container(
                      decoration: BoxDecoration(
                        color: const Color(0xFF285B5B),
                        shape: BoxShape.circle,
                        border: Border.all(color: Colors.white, width: 4),
                      ),
                      child: const Icon(Icons.sailing, color: Colors.white),
                    ),
                  ),
                ],
              ),
          ],
        ),

        Positioned(
          left: 18,
          right: 18,
          bottom: 20,
          child: Container(
            padding: const EdgeInsets.all(18),
            decoration: BoxDecoration(
              color: Colors.white.withValues(alpha: .96),
              borderRadius: BorderRadius.circular(25),
              boxShadow: const [
                BoxShadow(blurRadius: 20, color: Colors.black12),
              ],
            ),
            child: Column(
              children: [
                Row(
                  children: [
                    Expanded(
                      child: _journeyStat(
                        'DISTANCE',
                        '${(distanceMeters / 1000).toStringAsFixed(2)} km',
                      ),
                    ),
                    Expanded(child: _journeyStat('POINTS', '${route.length}')),
                    Expanded(
                      child: _journeyStat(
                        'STATUS',
                        tracking ? 'LIVE' : 'READY',
                      ),
                    ),
                  ],
                ),

                const SizedBox(height: 15),

                SizedBox(
                  width: double.infinity,
                  height: 48,
                  child: ElevatedButton.icon(
                    onPressed: tracking ? stopTracking : startTracking,
                    style: ElevatedButton.styleFrom(
                      backgroundColor: const Color(0xFF285B5B),
                      foregroundColor: Colors.white,
                      shape: RoundedRectangleBorder(
                        borderRadius: BorderRadius.circular(16),
                      ),
                    ),
                    icon: Icon(tracking ? Icons.stop : Icons.play_arrow),
                    label: Text(tracking ? 'STOP JOURNEY' : 'START JOURNEY'),
                  ),
                ),
              ],
            ),
          ),
        ),
      ],
    );
  }

  Widget _journeyStat(String title, String value) {
    return Column(
      children: [
        Text(
          value,
          style: const TextStyle(
            fontSize: 15,
            fontWeight: FontWeight.w700,
            color: Color(0xFF285B5B),
          ),
        ),
        const SizedBox(height: 4),
        Text(
          title,
          style: TextStyle(
            fontSize: 8,
            letterSpacing: 1,
            color: Colors.grey.shade500,
          ),
        ),
      ],
    );
  }
}

// ============================================================================
// SEA PAINTER
// ============================================================================

class SeaPainter extends CustomPainter {
  final double progress;

  SeaPainter({required this.progress});

  @override
  void paint(Canvas canvas, Size size) {
    final rect = Offset.zero & size;

    final background = const LinearGradient(
      begin: Alignment.topLeft,
      end: Alignment.bottomRight,
      colors: [Color(0xFF14373A), Color(0xFF1C5054), Color(0xFF286669)],
    );

    final paint = Paint()..shader = background.createShader(rect);

    canvas.drawRect(rect, paint);

    _glow(canvas, Offset(size.width * .82, size.height * .16), 105);

    _waves(canvas, size, progress, size.height * .72, 10);

    _waves(canvas, size, progress + .28, size.height * .81, 7);

    _particles(canvas, size, progress);

    _boat(canvas, size, progress);
  }

  void _glow(Canvas canvas, Offset center, double radius) {
    final paint = Paint()
      ..shader = RadialGradient(
        colors: [
          const Color(0xFF9ED8C9).withValues(alpha: .10),
          Colors.transparent,
        ],
      ).createShader(Rect.fromCircle(center: center, radius: radius));

    canvas.drawCircle(center, radius, paint);
  }

  void _waves(
    Canvas canvas,
    Size size,
    double value,
    double baseY,
    double height,
  ) {
    final path = ui.Path();

    path.moveTo(0.0, baseY);

    for (double x = 0; x <= size.width + 20; x += 18) {
      final y = baseY + math.sin((x / 58) + value * math.pi * 2) * height;

      path.lineTo(x, y);
    }

    path.lineTo(size.width, size.height);

    path.lineTo(0.0, size.height);

    path.close();

    canvas.drawPath(
      path,
      Paint()..color = Colors.white.withValues(alpha: .035),
    );
  }

  void _particles(Canvas canvas, Size size, double value) {
    final paint = Paint()..color = Colors.white.withValues(alpha: .09);

    for (int i = 0; i < 18; i++) {
      final x = ((i * 71) % size.width.toInt()).toDouble();

      final y = ((i * 43) + value * size.height) % size.height;

      canvas.drawCircle(Offset(x, y), 1.1, paint);
    }
  }

  // ==========================================================================
  // FIXED BOAT DRAWING
  // ==========================================================================

  void _boat(Canvas canvas, Size size, double value) {
    final bob = math.sin(value * math.pi * 2) * 3;

    final center = Offset(size.width * .51, size.height * .55 + bob);

    final glow = Paint()
      ..color = const Color(0xFF9ED8C9).withValues(alpha: .07);

    canvas.drawCircle(center, 42, glow);

    // IMPORTANT:
    // Explicit ui.Path avoids conflict
    // with latlong2 Path.

    final hull = ui.Path();

    hull.moveTo(center.dx - 29.0, center.dy);

    hull.lineTo(center.dx + 27.0, center.dy);

    hull.lineTo(center.dx + 14.0, center.dy + 13.0);

    hull.lineTo(center.dx - 18.0, center.dy + 13.0);

    hull.close();

    canvas.drawPath(hull, Paint()..color = const Color(0xFFF0E7D3));

    // Mast

    final mast = Paint()
      ..color = const Color(0xFFE4D9C4)
      ..strokeWidth = 2.0;

    canvas.drawLine(
      Offset(center.dx, center.dy),
      Offset(center.dx, center.dy - 27.0),
      mast,
    );

    // Sail

    final sail = ui.Path();

    sail.moveTo(center.dx + 1.0, center.dy - 25.0);

    sail.lineTo(center.dx + 1.0, center.dy - 6.0);

    sail.lineTo(center.dx + 19.0, center.dy - 6.0);

    sail.close();

    canvas.drawPath(sail, Paint()..color = const Color(0xFFA3D6C8));
  }

  @override
  bool shouldRepaint(covariant SeaPainter oldDelegate) {
    return oldDelegate.progress != progress;
  }
}

// ============================================================================
// PULSE PAINTER
// ============================================================================

class PulsePainter extends CustomPainter {
  final double risk;

  PulsePainter({required this.risk});

  @override
  void paint(Canvas canvas, Size size) {
    final center = Offset(size.width / 2, size.height / 2);

    final radius = size.width / 2 - 9;

    final basePaint = Paint()
      ..style = PaintingStyle.stroke
      ..strokeWidth = 9
      ..color = const Color(0xFFE5ECE7);

    canvas.drawCircle(center, radius, basePaint);

    final activePaint = Paint()
      ..style = PaintingStyle.stroke
      ..strokeWidth = 9
      ..strokeCap = StrokeCap.round
      ..color = const Color(0xFF5D9B8C);

    final sweep = math.pi * 2 * (risk / 100);

    canvas.drawArc(
      Rect.fromCircle(center: center, radius: radius),
      -math.pi / 2,
      sweep,
      false,
      activePaint,
    );

    if (risk > 0) {
      final markerPaint = Paint()..color = const Color(0xFF285B5B);

      final angle = -math.pi / 2 + sweep;

      final marker = Offset(
        center.dx + math.cos(angle) * radius,
        center.dy + math.sin(angle) * radius,
      );

      canvas.drawCircle(marker, 6, markerPaint);
    }
  }

  @override
  bool shouldRepaint(covariant PulsePainter oldDelegate) {
    return oldDelegate.risk != risk;
  }
}
