import 'dart:convert';

import 'package:flutter/material.dart';
import 'package:http/http.dart' as http;
import 'main.dart';

class MarineProfilePage extends StatefulWidget {
  final String email;
  final String token;
  final String name;

  const MarineProfilePage({
    super.key,
    required this.email,
    required this.token,
    required this.name,
  });

  @override
  State<MarineProfilePage> createState() => _MarineProfilePageState();
}

class _MarineProfilePageState extends State<MarineProfilePage> {
  static const String apiBaseUrl = 'https://marineintelligence.onrender.com';

  final familyNameController = TextEditingController();
  final familyNumberController = TextEditingController();
  final boatNameController = TextEditingController();

  String userType = 'Fisherman';
  String preferredLanguage = 'English';
  String relationship = 'Father';
  String boatType = 'Fishing Boat';

  bool loading = false;

  final List<String> userTypes = [
    'Fisherman',
    'Officer',
    'Scientist',
    'Ocean Researcher',
    'Cruise Member',
    'Other',
  ];

  final List<String> languages = ['English', 'Hindi', 'Marathi'];

  final List<String> relationships = [
    'Father',
    'Mother',
    'Brother',
    'Sister',
    'Spouse',
    'Friend',
    'Other',
  ];

  final List<String> boatTypes = [
    'Fishing Boat',
    'Cargo Boat',
    'Cruise Boat',
    'Research Vessel',
    'Speed Boat',
    'Other',
  ];

  @override
  void dispose() {
    familyNameController.dispose();
    familyNumberController.dispose();
    boatNameController.dispose();
    super.dispose();
  }

  Future<void> saveProfile() async {
    final familyName = familyNameController.text.trim();
    final familyNumber = familyNumberController.text.trim();
    final boatName = boatNameController.text.trim();

    if (familyName.isEmpty) {
      showMessage('Please enter family/friend name.');
      return;
    }

    if (familyNumber.isEmpty) {
      showMessage('Please enter emergency contact number.');
      return;
    }

    if (familyNumber.length < 10) {
      showMessage('Please enter a valid mobile number.');
      return;
    }

    setState(() {
      loading = true;
    });

    try {
      final response = await http
          .post(
            Uri.parse('$apiBaseUrl/profile'),
            headers: {
              'Content-Type': 'application/json',
              'Authorization': 'Bearer ${widget.token}',
            },
            body: jsonEncode({
              'email': widget.email,
              'user_type': userType,
              'preferred_language': preferredLanguage,
              'family_contact_name': familyName,
              'family_contact_number': familyNumber,
              'relationship': relationship,
              'boat_name': boatName.isEmpty ? null : boatName,
              'boat_type': boatName.isEmpty ? null : boatType,
            }),
          )
          .timeout(const Duration(seconds: 20));

      final data = jsonDecode(response.body);

      if (response.statusCode >= 200 && response.statusCode < 300) {
        if (!mounted) return;

        showMessage('Marine profile saved successfully.');

        await Future.delayed(const Duration(milliseconds: 700));

        if (!mounted) return;

        Navigator.pushAndRemoveUntil(
          context,
          MaterialPageRoute(builder: (_) => MarineHome(userName: widget.name)),
          (route) => false,
        );
      } else {
        final message =
            data['detail'] ?? data['message'] ?? 'Unable to save profile.';

        showMessage(message.toString());
      }
    } catch (e) {
      showMessage('Unable to connect to server. Please try again.');
    } finally {
      if (mounted) {
        setState(() {
          loading = false;
        });
      }
    }
  }

  void showMessage(String message) {
    if (!mounted) return;

    ScaffoldMessenger.of(context).showSnackBar(
      SnackBar(content: Text(message), behavior: SnackBarBehavior.floating),
    );
  }

  Widget buildDropdown({
    required String label,
    required String value,
    required List<String> items,
    required ValueChanged<String?> onChanged,
  }) {
    return DropdownButtonFormField<String>(
      initialValue: value,
      decoration: InputDecoration(
        labelText: label,
        filled: true,
        fillColor: Colors.white,
        border: OutlineInputBorder(
          borderRadius: BorderRadius.circular(16),
          borderSide: BorderSide.none,
        ),
      ),
      items: items.map((item) {
        return DropdownMenuItem(value: item, child: Text(item));
      }).toList(),
      onChanged: onChanged,
    );
  }

  @override
  Widget build(BuildContext context) {
    const dark = Color(0xFF183B3D);
    const teal = Color(0xFF285B5B);
    const bg = Color(0xFFF3F6F1);

    return Scaffold(
      backgroundColor: bg,

      appBar: AppBar(
        backgroundColor: bg,
        elevation: 0,
        foregroundColor: dark,
        title: const Text(
          'Marine Profile',
          style: TextStyle(fontWeight: FontWeight.w700),
        ),
      ),

      body: SafeArea(
        child: SingleChildScrollView(
          padding: const EdgeInsets.all(24),

          child: Column(
            crossAxisAlignment: CrossAxisAlignment.start,

            children: [
              const Text(
                'Complete your profile',
                style: TextStyle(
                  fontSize: 28,
                  fontWeight: FontWeight.w700,
                  color: dark,
                ),
              ),

              const SizedBox(height: 8),

              Text(
                'Tell us a little about yourself and your emergency contact.',
                style: TextStyle(fontSize: 14, color: Colors.grey.shade600),
              ),

              const SizedBox(height: 28),

              const Text(
                'Marine Role',
                style: TextStyle(
                  fontSize: 18,
                  fontWeight: FontWeight.w700,
                  color: dark,
                ),
              ),

              const SizedBox(height: 12),

              buildDropdown(
                label: 'User Type',
                value: userType,
                items: userTypes,
                onChanged: (value) {
                  if (value == null) return;

                  setState(() {
                    userType = value;
                  });
                },
              ),

              const SizedBox(height: 16),

              buildDropdown(
                label: 'Preferred Language',
                value: preferredLanguage,
                items: languages,
                onChanged: (value) {
                  if (value == null) return;

                  setState(() {
                    preferredLanguage = value;
                  });
                },
              ),

              const SizedBox(height: 30),

              const Text(
                'Emergency Contact',
                style: TextStyle(
                  fontSize: 18,
                  fontWeight: FontWeight.w700,
                  color: dark,
                ),
              ),

              const SizedBox(height: 12),

              TextField(
                controller: familyNameController,
                decoration: InputDecoration(
                  labelText: 'Family / Friend Name',
                  filled: true,
                  fillColor: Colors.white,
                  border: OutlineInputBorder(
                    borderRadius: BorderRadius.circular(16),
                    borderSide: BorderSide.none,
                  ),
                ),
              ),

              const SizedBox(height: 16),

              TextField(
                controller: familyNumberController,
                keyboardType: TextInputType.phone,
                maxLength: 10,
                decoration: InputDecoration(
                  labelText: 'Mobile Number',
                  counterText: '',
                  filled: true,
                  fillColor: Colors.white,
                  border: OutlineInputBorder(
                    borderRadius: BorderRadius.circular(16),
                    borderSide: BorderSide.none,
                  ),
                ),
              ),

              const SizedBox(height: 16),

              buildDropdown(
                label: 'Relationship',
                value: relationship,
                items: relationships,
                onChanged: (value) {
                  if (value == null) return;

                  setState(() {
                    relationship = value;
                  });
                },
              ),

              const SizedBox(height: 30),

              const Text(
                'Boat Details',
                style: TextStyle(
                  fontSize: 18,
                  fontWeight: FontWeight.w700,
                  color: dark,
                ),
              ),

              const SizedBox(height: 12),

              TextField(
                controller: boatNameController,
                decoration: InputDecoration(
                  labelText: 'Boat Name (Optional)',
                  filled: true,
                  fillColor: Colors.white,
                  border: OutlineInputBorder(
                    borderRadius: BorderRadius.circular(16),
                    borderSide: BorderSide.none,
                  ),
                ),
              ),

              const SizedBox(height: 16),

              buildDropdown(
                label: 'Boat Type',
                value: boatType,
                items: boatTypes,
                onChanged: (value) {
                  if (value == null) return;

                  setState(() {
                    boatType = value;
                  });
                },
              ),

              const SizedBox(height: 32),

              SizedBox(
                width: double.infinity,
                height: 54,

                child: FilledButton(
                  onPressed: loading ? null : saveProfile,

                  style: FilledButton.styleFrom(
                    backgroundColor: teal,
                    shape: RoundedRectangleBorder(
                      borderRadius: BorderRadius.circular(18),
                    ),
                  ),

                  child: loading
                      ? const SizedBox(
                          width: 23,
                          height: 23,
                          child: CircularProgressIndicator(
                            strokeWidth: 2.5,
                            color: Colors.white,
                          ),
                        )
                      : const Text(
                          'SAVE & CONTINUE',
                          style: TextStyle(
                            fontWeight: FontWeight.w700,
                            letterSpacing: 0.8,
                          ),
                        ),
                ),
              ),

              const SizedBox(height: 20),
            ],
          ),
        ),
      ),
    );
  }
}
