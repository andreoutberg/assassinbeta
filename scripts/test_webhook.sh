#!/bin/bash

# Andre Assassin Webhook Testing Script
# Tests webhook endpoint with various payloads and sources

set -e

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
CYAN='\033[0;36m'
NC='\033[0m' # No Color

# Configuration
WEBHOOK_URL="${WEBHOOK_URL:-http://localhost:8000/webhook}"
WEBHOOK_SECRET="${WEBHOOK_SECRET:-}"
VERBOSE="${VERBOSE:-false}"
LOG_FILE="${LOG_FILE:-webhook_test_$(date +%Y%m%d_%H%M%S).log}"

# Test counters
TOTAL_TESTS=0
PASSED_TESTS=0
FAILED_TESTS=0

# Function to print colored output
print_header() {
    echo ""
    echo -e "${CYAN}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
    echo -e "${CYAN}$1${NC}"
    echo -e "${CYAN}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
}

print_test() {
    echo -n -e "${BLUE}[TEST]${NC} $1... "
}

print_success() {
    echo -e "${GREEN}✓ PASS${NC}"
    ((PASSED_TESTS++))
    ((TOTAL_TESTS++))
}

print_fail() {
    echo -e "${RED}✗ FAIL${NC} - $1"
    ((FAILED_TESTS++))
    ((TOTAL_TESTS++))
}

print_info() {
    echo -e "  ${BLUE}ℹ${NC} $1"
}

print_verbose() {
    if [ "$VERBOSE" = "true" ]; then
        echo -e "  ${YELLOW}►${NC} $1"
    fi
}

# Function to generate HMAC signature
generate_signature() {
    local payload=$1
    if [ ! -z "$WEBHOOK_SECRET" ]; then
        echo -n "$payload" | openssl dgst -sha256 -hmac "$WEBHOOK_SECRET" -binary | base64
    fi
}

# Function to test basic webhook
test_basic_webhook() {
    print_test "Basic webhook connectivity"

    # Simple test payload
    PAYLOAD='{"test": true, "timestamp": "'$(date -u +%Y-%m-%dT%H:%M:%SZ)'", "source": "test_script"}'

    # Send request
    RESPONSE=$(curl -s -w "\n%{http_code}" -X POST "$WEBHOOK_URL" \
        -H "Content-Type: application/json" \
        -d "$PAYLOAD" 2>/dev/null)

    HTTP_CODE=$(echo "$RESPONSE" | tail -n1)
    BODY=$(echo "$RESPONSE" | head -n-1)

    print_verbose "Payload: $PAYLOAD"
    print_verbose "Response code: $HTTP_CODE"
    print_verbose "Response body: $BODY"

    if [[ "$HTTP_CODE" =~ ^(200|201|202|204)$ ]]; then
        print_success
        print_info "Response: HTTP $HTTP_CODE"
    else
        print_fail "HTTP $HTTP_CODE"
        [ ! -z "$BODY" ] && print_info "Response: $BODY"
    fi
}

# Function to test GitHub webhook
test_github_webhook() {
    print_test "GitHub webhook format"

    # GitHub push event payload
    PAYLOAD='{
        "ref": "refs/heads/main",
        "repository": {
            "name": "test-repo",
            "full_name": "user/test-repo",
            "html_url": "https://github.com/user/test-repo"
        },
        "pusher": {
            "name": "testuser",
            "email": "test@example.com"
        },
        "commits": [
            {
                "id": "abc123",
                "message": "Test commit",
                "timestamp": "'$(date -u +%Y-%m-%dT%H:%M:%SZ)'",
                "url": "https://github.com/user/test-repo/commit/abc123"
            }
        ]
    }'

    # GitHub headers
    SIGNATURE=$(generate_signature "$PAYLOAD")

    RESPONSE=$(curl -s -w "\n%{http_code}" -X POST "$WEBHOOK_URL" \
        -H "Content-Type: application/json" \
        -H "X-GitHub-Event: push" \
        -H "X-GitHub-Delivery: $(uuidgen 2>/dev/null || echo "test-delivery-id")" \
        ${SIGNATURE:+-H "X-Hub-Signature-256: sha256=$SIGNATURE"} \
        -d "$PAYLOAD" 2>/dev/null)

    HTTP_CODE=$(echo "$RESPONSE" | tail -n1)

    print_verbose "Event type: push"
    print_verbose "Response code: $HTTP_CODE"

    if [[ "$HTTP_CODE" =~ ^(200|201|202|204)$ ]]; then
        print_success
        print_info "GitHub push event accepted"
    else
        print_fail "HTTP $HTTP_CODE"
    fi
}

# Function to test GitLab webhook
test_gitlab_webhook() {
    print_test "GitLab webhook format"

    # GitLab push event payload
    PAYLOAD='{
        "object_kind": "push",
        "event_name": "push",
        "ref": "refs/heads/main",
        "project": {
            "name": "test-project",
            "path_with_namespace": "user/test-project",
            "web_url": "https://gitlab.com/user/test-project"
        },
        "commits": [
            {
                "id": "def456",
                "message": "Test commit",
                "timestamp": "'$(date -u +%Y-%m-%dT%H:%M:%SZ)'",
                "url": "https://gitlab.com/user/test-project/-/commit/def456"
            }
        ],
        "user_name": "Test User",
        "user_email": "test@example.com"
    }'

    RESPONSE=$(curl -s -w "\n%{http_code}" -X POST "$WEBHOOK_URL" \
        -H "Content-Type: application/json" \
        -H "X-Gitlab-Event: Push Hook" \
        -H "X-Gitlab-Token: ${WEBHOOK_SECRET:-test-token}" \
        -d "$PAYLOAD" 2>/dev/null)

    HTTP_CODE=$(echo "$RESPONSE" | tail -n1)

    print_verbose "Event type: Push Hook"
    print_verbose "Response code: $HTTP_CODE"

    if [[ "$HTTP_CODE" =~ ^(200|201|202|204)$ ]]; then
        print_success
        print_info "GitLab push event accepted"
    else
        print_fail "HTTP $HTTP_CODE"
    fi
}

# Function to test Bitbucket webhook
test_bitbucket_webhook() {
    print_test "Bitbucket webhook format"

    # Bitbucket push event payload
    PAYLOAD='{
        "push": {
            "changes": [
                {
                    "new": {
                        "type": "branch",
                        "name": "main",
                        "target": {
                            "hash": "ghi789",
                            "message": "Test commit",
                            "date": "'$(date -u +%Y-%m-%dT%H:%M:%SZ)'"
                        }
                    }
                }
            ]
        },
        "repository": {
            "name": "test-repo",
            "full_name": "user/test-repo",
            "links": {
                "html": {
                    "href": "https://bitbucket.org/user/test-repo"
                }
            }
        },
        "actor": {
            "display_name": "Test User"
        }
    }'

    RESPONSE=$(curl -s -w "\n%{http_code}" -X POST "$WEBHOOK_URL" \
        -H "Content-Type: application/json" \
        -H "X-Event-Key: repo:push" \
        -d "$PAYLOAD" 2>/dev/null)

    HTTP_CODE=$(echo "$RESPONSE" | tail -n1)

    print_verbose "Event type: repo:push"
    print_verbose "Response code: $HTTP_CODE"

    if [[ "$HTTP_CODE" =~ ^(200|201|202|204)$ ]]; then
        print_success
        print_info "Bitbucket push event accepted"
    else
        print_fail "HTTP $HTTP_CODE"
    fi
}

# Function to test custom webhook
test_custom_webhook() {
    print_test "Custom webhook format"

    # Custom payload
    PAYLOAD='{
        "event": "custom_event",
        "action": "test_action",
        "data": {
            "id": "12345",
            "name": "Test Item",
            "value": 42,
            "nested": {
                "field1": "value1",
                "field2": "value2"
            }
        },
        "metadata": {
            "source": "test_script",
            "version": "1.0",
            "timestamp": "'$(date -u +%Y-%m-%dT%H:%M:%SZ)'"
        }
    }'

    RESPONSE=$(curl -s -w "\n%{http_code}" -X POST "$WEBHOOK_URL" \
        -H "Content-Type: application/json" \
        -H "X-Custom-Header: test-value" \
        ${WEBHOOK_SECRET:+-H "Authorization: Bearer $WEBHOOK_SECRET"} \
        -d "$PAYLOAD" 2>/dev/null)

    HTTP_CODE=$(echo "$RESPONSE" | tail -n1)

    print_verbose "Custom event"
    print_verbose "Response code: $HTTP_CODE"

    if [[ "$HTTP_CODE" =~ ^(200|201|202|204)$ ]]; then
        print_success
        print_info "Custom event accepted"
    else
        print_fail "HTTP $HTTP_CODE"
    fi
}

# Function to test large payload
test_large_payload() {
    print_test "Large payload handling"

    # Generate large payload (1MB)
    LARGE_DATA=$(python3 -c "print('x' * 1000000)" 2>/dev/null || perl -e "print 'x' x 1000000")
    PAYLOAD='{"test": "large", "data": "'$LARGE_DATA'"}'

    RESPONSE=$(curl -s -w "\n%{http_code}" -X POST "$WEBHOOK_URL" \
        -H "Content-Type: application/json" \
        -d "$PAYLOAD" \
        --max-time 30 2>/dev/null)

    HTTP_CODE=$(echo "$RESPONSE" | tail -n1)

    print_verbose "Payload size: ~1MB"
    print_verbose "Response code: $HTTP_CODE"

    if [[ "$HTTP_CODE" =~ ^(200|201|202|204|413)$ ]]; then
        if [ "$HTTP_CODE" = "413" ]; then
            print_success
            print_info "Large payload rejected as expected (413 Payload Too Large)"
        else
            print_success
            print_info "Large payload accepted"
        fi
    else
        print_fail "Unexpected response: HTTP $HTTP_CODE"
    fi
}

# Function to test invalid JSON
test_invalid_json() {
    print_test "Invalid JSON handling"

    PAYLOAD='{"invalid": json"}'

    RESPONSE=$(curl -s -w "\n%{http_code}" -X POST "$WEBHOOK_URL" \
        -H "Content-Type: application/json" \
        -d "$PAYLOAD" 2>/dev/null)

    HTTP_CODE=$(echo "$RESPONSE" | tail -n1)

    print_verbose "Malformed JSON sent"
    print_verbose "Response code: $HTTP_CODE"

    if [ "$HTTP_CODE" = "400" ]; then
        print_success
        print_info "Invalid JSON rejected as expected (400 Bad Request)"
    else
        print_fail "Expected 400, got HTTP $HTTP_CODE"
    fi
}

# Function to test rate limiting
test_rate_limiting() {
    print_test "Rate limiting"

    SUCCESS_COUNT=0
    RATE_LIMITED=false

    # Send 20 rapid requests
    for i in {1..20}; do
        RESPONSE=$(curl -s -o /dev/null -w "%{http_code}" -X POST "$WEBHOOK_URL" \
            -H "Content-Type: application/json" \
            -d '{"test": "rate_limit", "request": '$i'}' 2>/dev/null)

        if [ "$RESPONSE" = "429" ]; then
            RATE_LIMITED=true
            break
        elif [[ "$RESPONSE" =~ ^(200|201|202|204)$ ]]; then
            ((SUCCESS_COUNT++))
        fi
    done

    print_verbose "Successful requests: $SUCCESS_COUNT"

    if [ "$RATE_LIMITED" = "true" ]; then
        print_success
        print_info "Rate limiting active (429 Too Many Requests after $SUCCESS_COUNT requests)"
    elif [ "$SUCCESS_COUNT" -eq 20 ]; then
        print_success
        print_info "No rate limiting detected (all 20 requests succeeded)"
    else
        print_fail "Unexpected behavior"
    fi
}

# Function to check webhook logs
check_webhook_logs() {
    print_test "Checking webhook processing in logs"

    # Check backend logs for webhook processing
    if docker ps | grep -q "backend"; then
        RECENT_LOGS=$(docker logs backend --tail 100 2>&1 | grep -i "webhook" | tail -5)

        if [ ! -z "$RECENT_LOGS" ]; then
            print_success
            print_info "Webhook activity found in logs"
            if [ "$VERBOSE" = "true" ]; then
                echo "$RECENT_LOGS" | while read line; do
                    print_verbose "$line"
                done
            fi
        else
            print_fail "No webhook activity in recent logs"
        fi
    else
        print_fail "Backend container not running"
    fi
}

# Function to test webhook with authentication
test_authenticated_webhook() {
    print_test "Authenticated webhook"

    # Test with authentication header
    PAYLOAD='{"test": "auth", "timestamp": "'$(date -u +%Y-%m-%dT%H:%M:%SZ)'"}'

    if [ ! -z "$WEBHOOK_SECRET" ]; then
        RESPONSE=$(curl -s -w "\n%{http_code}" -X POST "$WEBHOOK_URL" \
            -H "Content-Type: application/json" \
            -H "Authorization: Bearer $WEBHOOK_SECRET" \
            -d "$PAYLOAD" 2>/dev/null)
    else
        RESPONSE=$(curl -s -w "\n%{http_code}" -X POST "$WEBHOOK_URL" \
            -H "Content-Type: application/json" \
            -H "X-API-Key: test-api-key" \
            -d "$PAYLOAD" 2>/dev/null)
    fi

    HTTP_CODE=$(echo "$RESPONSE" | tail -n1)

    print_verbose "Authentication header sent"
    print_verbose "Response code: $HTTP_CODE"

    if [[ "$HTTP_CODE" =~ ^(200|201|202|204)$ ]]; then
        print_success
        print_info "Authenticated request accepted"
    else
        print_fail "HTTP $HTTP_CODE"
    fi
}

# Function to print summary
print_summary() {
    print_header "WEBHOOK TEST SUMMARY"

    echo ""
    echo -e "Webhook URL:     ${BLUE}$WEBHOOK_URL${NC}"
    echo -e "Total Tests:     ${BLUE}$TOTAL_TESTS${NC}"
    echo -e "Passed:          ${GREEN}$PASSED_TESTS${NC}"
    echo -e "Failed:          ${RED}$FAILED_TESTS${NC}"
    echo ""

    if [ "$FAILED_TESTS" -eq 0 ]; then
        echo -e "${GREEN}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
        echo -e "${GREEN}      ALL WEBHOOK TESTS PASSED${NC}"
        echo -e "${GREEN}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
        return 0
    else
        echo -e "${RED}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
        echo -e "${RED}     SOME WEBHOOK TESTS FAILED${NC}"
        echo -e "${RED}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
        return 1
    fi
}

# Function to show usage
show_usage() {
    echo "Usage: $0 [OPTIONS]"
    echo ""
    echo "Options:"
    echo "  -u, --url URL          Webhook URL (default: http://localhost:8000/webhook)"
    echo "  -s, --secret SECRET    Webhook secret for authentication"
    echo "  -v, --verbose          Enable verbose output"
    echo "  -t, --test TEST        Run specific test only (basic|github|gitlab|bitbucket|custom|large|invalid|rate|auth|logs)"
    echo "  -h, --help             Show this help message"
    echo ""
    echo "Examples:"
    echo "  $0                                    # Run all tests with default URL"
    echo "  $0 -u http://api.example.com/webhook  # Test specific URL"
    echo "  $0 -t github -v                       # Run GitHub test with verbose output"
    echo "  $0 -s mysecret                        # Test with authentication secret"
}

# Parse command line arguments
parse_args() {
    while [[ $# -gt 0 ]]; do
        case $1 in
            -u|--url)
                WEBHOOK_URL="$2"
                shift 2
                ;;
            -s|--secret)
                WEBHOOK_SECRET="$2"
                shift 2
                ;;
            -v|--verbose)
                VERBOSE=true
                shift
                ;;
            -t|--test)
                SPECIFIC_TEST="$2"
                shift 2
                ;;
            -h|--help)
                show_usage
                exit 0
                ;;
            *)
                echo "Unknown option: $1"
                show_usage
                exit 1
                ;;
        esac
    done
}

# Main execution
main() {
    parse_args "$@"

    echo -e "${CYAN}╔════════════════════════════════════════╗${NC}"
    echo -e "${CYAN}║    Andre Assassin Webhook Tester      ║${NC}"
    echo -e "${CYAN}║        $(date '+%Y-%m-%d %H:%M:%S')         ║${NC}"
    echo -e "${CYAN}╚════════════════════════════════════════╝${NC}"

    # Check if curl is available
    if ! command -v curl &> /dev/null; then
        echo -e "${RED}Error: curl is not installed${NC}"
        exit 1
    fi

    # Run tests based on selection
    if [ ! -z "$SPECIFIC_TEST" ]; then
        case $SPECIFIC_TEST in
            basic) test_basic_webhook ;;
            github) test_github_webhook ;;
            gitlab) test_gitlab_webhook ;;
            bitbucket) test_bitbucket_webhook ;;
            custom) test_custom_webhook ;;
            large) test_large_payload ;;
            invalid) test_invalid_json ;;
            rate) test_rate_limiting ;;
            auth) test_authenticated_webhook ;;
            logs) check_webhook_logs ;;
            *)
                echo "Unknown test: $SPECIFIC_TEST"
                exit 1
                ;;
        esac
    else
        # Run all tests
        print_header "WEBHOOK CONNECTIVITY"
        test_basic_webhook

        print_header "WEBHOOK FORMATS"
        test_github_webhook
        test_gitlab_webhook
        test_bitbucket_webhook
        test_custom_webhook

        print_header "EDGE CASES"
        test_large_payload
        test_invalid_json

        print_header "SECURITY"
        test_authenticated_webhook
        test_rate_limiting

        print_header "MONITORING"
        check_webhook_logs
    fi

    # Print summary
    print_summary
}

# Run main function
main "$@"