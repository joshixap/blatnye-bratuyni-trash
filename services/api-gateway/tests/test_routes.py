import pytest
from unittest.mock import patch, MagicMock


@patch('routes.user.requests.post')
def test_register_route(mock_post, test_client):
    """Test user registration through gateway"""
    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.content = b'{"message": "User created"}'
    mock_response.headers = {'content-type': 'application/json'}
    mock_post.return_value = mock_response
    
    response = test_client.post(
        "/users/register",
        json={
            "name": "Test User",
            "email": "test@example.com",
            "password": "password123"
        }
    )
    
    assert response.status_code == 200
    mock_post.assert_called_once()


@patch('routes.user.requests.post')
def test_login_route(mock_post, test_client):
    """Test user login through gateway"""
    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.content = b'{"access_token": "fake_token", "token_type": "bearer"}'
    mock_response.headers = {'content-type': 'application/json'}
    mock_post.return_value = mock_response
    
    response = test_client.post(
        "/users/login",
        json={
            "email": "test@example.com",
            "password": "password123"
        }
    )
    
    assert response.status_code == 200


@patch('routes.booking.requests.get')
def test_get_zones_route(mock_get, test_client):
    """Test getting zones through gateway"""
    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.content = b'[{"id": 1, "name": "Zone 1"}]'
    mock_response.headers = {'content-type': 'application/json'}
    mock_get.return_value = mock_response
    
    response = test_client.get("/bookings/zones")
    
    assert response.status_code == 200
    mock_get.assert_called_once()
