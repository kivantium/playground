from django.shortcuts import render
from social_django.models import UserSocialAuth

def index(request):
    if request.user.is_authenticated:
        user = UserSocialAuth.objects.get(user_id=request.user.id)
        return render(request,'hello/index.html', {'user': user})
    else:
        return render(request,'hello/index.html')
